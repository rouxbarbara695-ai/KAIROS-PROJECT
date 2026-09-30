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
#   KAIROS_ENV_FILE     configuration    (défaut infra/.env.production)

set -euo pipefail

BACKUP_DIR="${KAIROS_BACKUP_DIR:-/var/backups/kairos}"
KEY_FILE="${KAIROS_BACKUP_KEY:-/etc/kairos/backup.key}"
KEEP="${KAIROS_BACKUP_KEEP:-14}"
COMPOSE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docker-compose.prod.yml"
ENV_FILE="${KAIROS_ENV_FILE:-$(dirname "$COMPOSE_FILE")/.env.production}"

# Sans ce fichier, Docker Compose ne sait pas résoudre les variables que le
# fichier de composition déclare obligatoires (domaine, mot de passe de la
# base) et refuse de s'exécuter. Il ne le lit pas seul : il ne cherche que
# `.env`, pas `.env.production`. Une tâche planifiée qui ignorerait cela
# échouerait chaque nuit sans que personne le voie.
if [[ ! -r "$ENV_FILE" ]]; then
	echo "Configuration illisible : $ENV_FILE" >&2
	echo "Lancer avec sudo, ou indiquer un autre fichier : KAIROS_ENV_FILE=…" >&2
	exit 1
fi

compose() {
	docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

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
compose exec -T postgres \
	pg_dump --username kairos --format plain --no-owner kairos |
	gzip -9 |
	openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$KEY_FILE" \
		>"$temporaire"

# Une sauvegarde qu'on n'ouvre jamais n'est qu'une hypothèse. On vérifie ici
# ce qui l'est sans restaurer : que le fichier se déchiffre, se décompresse, et
# que le dump va **jusqu'au bout**. `pg_dump` écrit sa ligne de clôture en
# dernier : un dump interrompu ne l'a pas.
#
# On lit tout le flux, jusqu'à la fin. La version précédente coupait la lecture
# après 4 Ko (`head -c` puis `grep -q`) : l'étage en amont recevait SIGPIPE, et
# `pipefail` transformait ce signal en échec. Sur un vrai dump, une sauvegarde
# parfaitement bonne était déclarée inutilisable. Un dump minuscule, lui, tient
# dans le tampon du tube et ne déclenchait jamais le défaut. `tail` lit tout ;
# `grep -c` n'arrête pas sa lecture à la première ligne trouvée.
if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$KEY_FILE" \
	-in "$temporaire" | gunzip | tail -n 10 |
	grep -c "PostgreSQL database dump complete" >/dev/null; then
	echo "La sauvegarde ne se relit pas ou est incomplète : $destination n'a pas été créée." >&2
	exit 1
fi

# Le nom définitif n'est donné qu'à un fichier déjà vérifié : un fichier
# incomplet ne doit jamais porter un nom qu'on croirait valide.
mv "$temporaire" "$destination"
trap - EXIT

taille="$(du -h "$destination" | cut -f1)"
echo "Sauvegarde $destination ($taille) — relecture vérifiée."

# Rotation. `ls -t` trie du plus récent au plus ancien ; on supprime la queue.
mapfile -t anciennes < <(ls -t "$BACKUP_DIR"/kairos-*.sql.gz.enc 2>/dev/null | tail -n "+$((KEEP + 1))")
# `if` plutôt que `[[ … ]] && …` : quand il n'y a rien à supprimer, le test est
# faux, et ce « faux » deviendrait le code de sortie du script — une sauvegarde
# réussie annoncée comme un échec.
for fichier in "${anciennes[@]:-}"; do
	if [[ -n "$fichier" ]]; then
		rm -f "$fichier"
		echo "Rotation : $fichier supprimée."
	fi
done
