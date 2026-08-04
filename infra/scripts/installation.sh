#!/usr/bin/env bash
# Installation complète de KAIROS sur une machine neuve.
#
#   bash /opt/kairos/infra/scripts/installation.sh kairostask.fr
#
# Reprend, dans l'ordre, tout ce que décrit docs/delivery/deploiement.md :
# Docker, pare-feu, secrets, clé de sauvegarde, démarrage, tâche quotidienne.
# Le guide reste la référence — il explique *pourquoi*. Ce script fait, sans
# demander à qui l'exécute de comprendre chaque commande au moment où il la
# tape.
#
# **Réexécutable sans dégât.** C'est la propriété qui compte le plus ici : une
# installation s'interrompt (réseau coupé, image qui ne construit pas), et il
# faut pouvoir relancer sans se demander ce qui a déjà été fait. Les secrets ne
# sont donc tirés qu'une fois — les régénérer rendrait la base existante
# inaccessible et invaliderait les sessions ouvertes — et chaque étape vérifie
# son état avant d'agir.
#
# Ce que le script ne fait pas, délibérément : créer le compte utilisateur. Le
# mot de passe se saisit en invite masquée, et un mot de passe passé à un
# script finirait dans l'historique du shell.

set -euo pipefail

readonly RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly ENV_FILE="$RACINE/infra/.env.production"
readonly COMPOSE_FILE="$RACINE/infra/docker-compose.prod.yml"
readonly CLE_SAUVEGARDE="/etc/kairos/backup.key"

readonly VERT=$'\033[32m'
readonly JAUNE=$'\033[33m'
readonly ROUGE=$'\033[31m'
readonly GRAS=$'\033[1m'
readonly FIN=$'\033[0m'

etape() { printf '\n%s==> %s%s\n' "$GRAS" "$1" "$FIN"; }
ok() { printf '%s    ✓ %s%s\n' "$VERT" "$1" "$FIN"; }
info() { printf '      %s\n' "$1"; }
alerte() { printf '%s    ! %s%s\n' "$JAUNE" "$1" "$FIN"; }
erreur() {
	printf '%s\n    ✗ %s%s\n' "$ROUGE" "$1" "$FIN" >&2
	exit 1
}

compose() {
	docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

# --------------------------------------------------------------------------
# Contrôles préalables
# --------------------------------------------------------------------------

[[ $EUID -eq 0 ]] || erreur "À lancer en root : sudo bash $0 <domaine>"
[[ $# -eq 1 ]] || erreur "Usage : $0 <domaine>   (exemple : $0 kairostask.fr)"

readonly DOMAINE="$1"
[[ "$DOMAINE" =~ ^[a-z0-9.-]+\.[a-z]{2,}$ ]] ||
	erreur "« $DOMAINE » ne ressemble pas à un domaine. Ni https://, ni barre finale."

etape "Vérification du domaine"

# Le DNS d'abord, avant toute installation : Caddy demande le certificat dès
# son premier démarrage, et Let's Encrypt limite le nombre de tentatives par
# domaine et par semaine. Découvrir un DNS mal posé après cinq échecs coûte
# une semaine d'attente ; le découvrir maintenant coûte cinq minutes.
adresse_locale="$(curl -fsS --max-time 15 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"
resolue="$(getent ahostsv4 "$DOMAINE" 2>/dev/null | awk 'NR==1 {print $1}' || true)"

if [[ -z "$resolue" ]]; then
	erreur "$DOMAINE ne résout vers aucune adresse. Poser l'enregistrement A avant de continuer."
fi
info "$DOMAINE → $resolue"

if [[ -n "$adresse_locale" && "$resolue" != "$adresse_locale" && "${KAIROS_IGNORER_VERIF_DNS:-}" != "1" ]]; then
	alerte "Le domaine pointe vers $resolue, mais ce serveur se voit en $adresse_locale."
	alerte "Le certificat TLS échouerait, et chaque échec consomme un essai."
	info ""
	info "Si l'enregistrement A est faux : le corriger, puis relancer."
	info "Si ce serveur sort par une autre adresse que celle qu'il expose —"
	info "cela arrive derrière une passerelle — la vérification se trompe :"
	info "  KAIROS_IGNORER_VERIF_DNS=1 bash $0 $DOMAINE"
	erreur "Installation arrêtée avant la première demande de certificat."
fi
ok "Le domaine pointe bien vers ce serveur"

resolue_www="$(getent ahostsv4 "www.$DOMAINE" 2>/dev/null | awk 'NR==1 {print $1}' || true)"
if [[ -z "$resolue_www" ]]; then
	alerte "www.$DOMAINE ne résout pas : la redirection www ne fonctionnera pas."
	alerte "Sans gravité pour le site principal — Caddy réessaiera dans le vide."
else
	ok "www.$DOMAINE pointe vers $resolue_www"
fi

# --------------------------------------------------------------------------
# Docker
# --------------------------------------------------------------------------

etape "Docker"

if docker compose version >/dev/null 2>&1; then
	ok "déjà installé ($(docker --version | cut -d, -f1))"
else
	# `ID` et `VERSION_CODENAME` viennent de la distribution installée plutôt
	# que d'être écrits en dur : l'hébergeur ne propose pas toujours celle
	# qu'on avait prévue.
	# shellcheck disable=SC1091
	. /etc/os-release

	info "distribution détectée : $ID $VERSION_CODENAME"
	depot="https://download.docker.com/linux/$ID"
	code="$(curl -s -o /dev/null -w '%{http_code}' "$depot/dists/$VERSION_CODENAME/Release" || true)"
	[[ "$code" == "200" ]] ||
		erreur "Docker ne publie pas de paquets pour $ID $VERSION_CODENAME (HTTP $code). Réinstaller le serveur sur une version antérieure."

	export DEBIAN_FRONTEND=noninteractive
	apt-get update -qq
	apt-get install -y -qq ca-certificates curl git ufw openssl >/dev/null
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL "$depot/gpg" -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] $depot $VERSION_CODENAME stable" \
		>/etc/apt/sources.list.d/docker.list
	apt-get update -qq
	apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
		docker-buildx-plugin docker-compose-plugin >/dev/null
	ok "installé"
fi

# --------------------------------------------------------------------------
# Pare-feu
# --------------------------------------------------------------------------

etape "Pare-feu"

# `ufw allow OpenSSH` est posé **avant** l'activation : activer d'abord
# fermerait la session en cours, sur un serveur auquel on n'aurait plus accès.
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw --force enable >/dev/null
ok "seuls SSH, 80 et 443 entrent"
info "PostgreSQL et Redis n'ont de toute façon aucun port publié"

# --------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------

etape "Configuration"

if [[ -f "$ENV_FILE" ]]; then
	ok "$ENV_FILE existe déjà — conservé tel quel"
	info "Les secrets ne sont jamais régénérés : la base existante deviendrait"
	info "inaccessible et toutes les sessions seraient invalidées."
else
	umask 077
	cat >"$ENV_FILE" <<EOF
# Généré par infra/scripts/installation.sh le $(date -u +%Y-%m-%dT%H:%M:%SZ).
# Ne pas versionner. Ne pas régénérer les secrets sur une base existante.
KAIROS_DOMAIN=$DOMAINE
POSTGRES_PASSWORD=$(openssl rand -base64 36 | tr -d '\n')
CURSOR_SECRET=$(openssl rand -base64 36 | tr -d '\n')
LOG_LEVEL=INFO
ACTIVE_RULESET_VERSION=1.2.0
EOF
	chmod 600 "$ENV_FILE"
	ok "secrets tirés au sort et écrits dans $ENV_FILE (600)"
fi

# --------------------------------------------------------------------------
# Clé de sauvegarde
# --------------------------------------------------------------------------

etape "Clé de chiffrement des sauvegardes"

if [[ -f "$CLE_SAUVEGARDE" ]]; then
	ok "déjà présente"
else
	mkdir -p "$(dirname "$CLE_SAUVEGARDE")"
	(
		umask 077
		openssl rand -base64 48 >"$CLE_SAUVEGARDE"
	)
	chmod 600 "$CLE_SAUVEGARDE"
	ok "créée : $CLE_SAUVEGARDE"
fi
alerte "COPIER CETTE CLÉ HORS DU SERVEUR."
info "Une sauvegarde chiffrée dont la clé a brûlé avec le serveur ne vaut rien."
info "La lire :  cat $CLE_SAUVEGARDE"

# --------------------------------------------------------------------------
# Démarrage
# --------------------------------------------------------------------------

etape "Construction et démarrage"
info "La première construction compile l'interface : comptez plusieurs minutes."

chmod +x "$RACINE"/infra/scripts/*.sh
compose up -d --build

ok "conteneurs démarrés"
info "Le conteneur « migrate » s'arrête après avoir joué les migrations : c'est voulu."

# --------------------------------------------------------------------------
# Tâche de sauvegarde
# --------------------------------------------------------------------------

etape "Sauvegarde quotidienne"

cat >/etc/cron.d/kairos-sauvegarde <<EOF
# Sauvegarde chiffrée de KAIROS, quatorze jours d'historique.
17 3 * * * root $RACINE/infra/scripts/sauvegarde.sh >> /var/log/kairos-sauvegarde.log 2>&1
EOF
chmod 644 /etc/cron.d/kairos-sauvegarde
ok "installée : tous les jours à 03h17 UTC"

# --------------------------------------------------------------------------
# Attente du certificat
# --------------------------------------------------------------------------

etape "Certificat TLS"
info "Caddy le demande à Let's Encrypt ; cela prend de dix secondes à deux minutes."

sante=""
for _ in $(seq 1 40); do
	sante="$(curl -s --max-time 5 --resolve "$DOMAINE:443:127.0.0.1" \
		"https://$DOMAINE/api/v1/health" 2>/dev/null || true)"
	[[ "$sante" == *'"ok"'* ]] && break
	sleep 5
done

echo
if [[ "$sante" == *'"ok"'* ]]; then
	ok "https://$DOMAINE répond"
	printf '\n%s  KAIROS est en ligne : https://%s%s\n' "$GRAS$VERT" "$DOMAINE" "$FIN"
	printf '\n  Dernière étape — créer votre compte, en invite masquée :\n\n'
	printf '    cd %s && docker compose --env-file infra/.env.production \\\n' "$RACINE"
	printf '      -f infra/docker-compose.prod.yml exec api \\\n'
	printf '      python -m app.create_user votre.adresse@exemple.fr\n\n'
else
	alerte "Le site ne répond pas encore."
	info "Ce n'est pas nécessairement un échec : la construction peut être longue."
	info "Regarder ce qui se passe :"
	printf '\n    cd %s\n' "$RACINE"
	printf '    docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml ps\n'
	printf '    docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml logs --tail 50 caddy\n\n'
fi
