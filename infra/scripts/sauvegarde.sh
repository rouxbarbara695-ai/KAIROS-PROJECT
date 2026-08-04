#!/usr/bin/env bash
# Sauvegarde chiffrée de la base KAIROS.
#
# C'est la contrepartie d'un serveur à soi : personne d'autre ne le fera. Le
# registre de trésorerie, les analyses publiées et l'historique d'audit ne se
# reconstituent pas — ils sont, par construction, immuables et sans double.
#
# Chiffrée parce qu'une sauvegarde voyage : copiée ailleurs, elle échappe aux
# protections du serveur. Le dump contient des empreintes de mot de passe, des
# numéros de série (règle 11) et l'intégralité du portefeuille.
#
# Usage (voir docs/delivery/deploiement.md pour l'installation en tâche
# quotidienne) :
#
#   infra/scripts/sauvegarde.sh
#
# Variables :
#   KAIROS_BACKUP_DIR   destination        (défaut /var/backups/kairos)
#   KAIROS_BACKUP_KEY   fichier de passe   (défaut /etc/kairos/backup.key)
#   KAIROS_BACKUP_KEEP  nombre à conserver (défaut 14)

set -euo pipefail

BACKUP_DIR="${KAIROS_BACKUP_DIR:-/var/backups/kairos}"
KEY_FILE="${KAIROS_BACKUP_KEY:-/etc/kairos/backup.key}"
KEEP="${KAIROS_BACKUP_KEEP:-14}"
COMPOSE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docker-compose.prod.yml"

if [[ ! -r "$KEY_FILE" ]]; then
	echo "Clé de sauvegarde illisible : $KEY_FILE" >&2
	echo "La créer une fois : openssl rand -base64 48 > $KEY_FILE && chmod 600 $KEY_FILE" >&2
	exit 1
fi

mkdir -p "$BACKUP_DIR"
horodatage="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
destination="$BACKUP_DIR/kairos-$horodatage.sql.gz.enc"

# Écrit d'abord dans un fichier temporaire : une sauvegarde interrompue ne doit
# pas laisser derrière elle un fichier au nom correct et au contenu tronqué,
# qu'on croirait valide le jour où on en a besoin.
temporaire="$destination.partiel"
trap 'rm -f "$temporaire"' EXIT

# `pg_dump` dans le conteneur, chiffrement sur l'hôte : la clé n'entre jamais
# dans le conteneur de base de données.
docker compose -f "$COMPOSE_FILE" exec -T postgres \
	pg_dump --username kairos --format plain --no-owner kairos |
	gzip -9 |
	openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$KEY_FILE" \
		>"$temporaire"

mv "$temporaire" "$destination"
trap - EXIT

# Une sauvegarde qu'on n'ouvre jamais n'est qu'une hypothèse. On vérifie ici
# le seul point vérifiable sans restaurer : que le fichier se déchiffre et se
# décompresse, et qu'il contient bien du SQL.
if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$KEY_FILE" \
	-in "$destination" | gunzip | head -c 4096 | grep -q "PostgreSQL database dump"; then
	echo "La sauvegarde $destination ne se relit pas. Elle est inutilisable." >&2
	exit 1
fi

taille="$(du -h "$destination" | cut -f1)"
echo "Sauvegarde $destination ($taille) — relecture vérifiée."

# Rotation. `ls -t` trie du plus récent au plus ancien ; on supprime la queue.
mapfile -t anciennes < <(ls -t "$BACKUP_DIR"/kairos-*.sql.gz.enc 2>/dev/null | tail -n "+$((KEEP + 1))")
for fichier in "${anciennes[@]:-}"; do
	[[ -n "$fichier" ]] && rm -f "$fichier" && echo "Rotation : $fichier supprimée."
done
