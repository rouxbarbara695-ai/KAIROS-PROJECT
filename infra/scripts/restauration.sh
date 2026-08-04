#!/usr/bin/env bash
# Restauration d'une sauvegarde KAIROS.
#
# Ce script existe pour être **essayé avant d'en avoir besoin**. Une sauvegarde
# jamais restaurée n'est pas une sauvegarde : c'est un fichier dont on espère
# quelque chose. La procédure de vérification est décrite dans
# docs/delivery/deploiement.md.
#
#   infra/scripts/restauration.sh /var/backups/kairos/kairos-....sql.gz.enc
#
# La restauration **écrase** la base existante. Le script le dit et demande
# confirmation : se tromper de sens entre sauvegarde et restauration détruit
# précisément ce qu'on cherchait à protéger.

set -euo pipefail

KEY_FILE="${KAIROS_BACKUP_KEY:-/etc/kairos/backup.key}"
COMPOSE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docker-compose.prod.yml"

if [[ $# -ne 1 ]]; then
	echo "Usage : $0 <fichier de sauvegarde>" >&2
	exit 2
fi

archive="$1"
[[ -r "$archive" ]] || {
	echo "Sauvegarde illisible : $archive" >&2
	exit 1
}
[[ -r "$KEY_FILE" ]] || {
	echo "Clé illisible : $KEY_FILE" >&2
	exit 1
}

echo "Cette opération remplace TOUT le contenu de la base par $archive."
echo "Les données saisies depuis cette sauvegarde seront perdues."
read -r -p "Taper « restaurer » pour continuer : " confirmation
[[ "$confirmation" == "restaurer" ]] || {
	echo "Annulé."
	exit 1
}

# L'API est arrêtée pendant la restauration : la laisser écrire dans une base
# qu'on est en train de remplacer produirait un mélange des deux états.
docker compose -f "$COMPOSE_FILE" stop api web

# On repart d'une base vide plutôt que de superposer : un dump restauré
# par-dessus des données existantes échouerait sur chaque clé déjà présente et
# laisserait un état à moitié ancien, à moitié neuf.
docker compose -f "$COMPOSE_FILE" exec -T postgres \
	psql --username kairos --dbname postgres \
	-c "drop database if exists kairos_restauration;" \
	-c "create database kairos_restauration owner kairos;"

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$KEY_FILE" -in "$archive" |
	gunzip |
	docker compose -f "$COMPOSE_FILE" exec -T postgres \
		psql --username kairos --dbname kairos_restauration --quiet --set ON_ERROR_STOP=on

# La bascule n'a lieu qu'une fois le dump entièrement chargé : si quoi que ce
# soit échoue au-dessus, `set -e` arrête ici et la base d'origine est intacte.
docker compose -f "$COMPOSE_FILE" exec -T postgres \
	psql --username kairos --dbname postgres \
	-c "drop database if exists kairos_precedente;" \
	-c "alter database kairos rename to kairos_precedente;" \
	-c "alter database kairos_restauration rename to kairos;"

docker compose -f "$COMPOSE_FILE" start api web

echo "Restauration terminée. L'ancienne base est conservée sous « kairos_precedente »."
echo "La supprimer une fois la vérification faite :"
echo "  docker compose -f $COMPOSE_FILE exec -T postgres \\"
echo "    psql --username kairos --dbname postgres -c 'drop database kairos_precedente;'"
