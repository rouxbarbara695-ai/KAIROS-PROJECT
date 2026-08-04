# Déploiement de KAIROS

Décision **Q-02** : une machine unique, chez un hébergeur européen, avec
Docker Compose et Caddy. Ce document se suit ligne à ligne.

## Pourquoi une seule machine

KAIROS sert **un** utilisateur. Il n'y a aucun problème de charge à résoudre,
donc rien à gagner à payer de l'élasticité. Une plateforme managée
facturerait PostgreSQL et Redis séparément là où ce sont ici deux conteneurs
gratuits, et le coût dériverait avec l'usage.

Surtout, les données en jeu sont un portefeuille financier personnel et un
historique d'audit immuable. Une machine, une sauvegarde, aucun tiers.

La contrepartie est réelle et ne se contourne pas : **les sauvegardes et les
mises à jour vous appartiennent**. La section « Sauvegardes » n'est pas
facultative.

Coût attendu : environ 5 € par mois pour le serveur, environ 10 € par an pour
le domaine.

## Ce qu'il faut avant de commencer

1. **Un serveur.** Hetzner CX22 (2 vCPU, 4 Go, 40 Go) ou Scaleway DEV1-S
   conviennent largement. Debian 12 ou Ubuntu 24.04.
2. **Un nom de domaine**, acheté chez OVH, Gandi ou Porkbun.
3. **Un enregistrement DNS de type A** pointant le domaine vers l'adresse IP
   du serveur. À poser **avant** le premier démarrage : Caddy demande le
   certificat immédiatement, et Let's Encrypt limite le nombre de tentatives
   par domaine et par semaine. Vérifier depuis votre poste :

   ```bash
   dig +short kairos.exemple.fr
   ```

   La commande doit répondre l'adresse IP du serveur, et rien d'autre.

Sans HTTPS, il n'y a pas de connexion possible : le cookie de session est
marqué `Secure` hors développement local. Le domaine n'est donc pas un confort,
c'est la condition d'accès.

## Installation du serveur

En SSH sur le serveur, en root.

```bash
apt update && apt upgrade -y
apt install -y ca-certificates curl git ufw
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Le pare-feu. Seuls SSH et le web entrent ; tout le reste est refusé. PostgreSQL
et Redis n'ont de toute façon aucun port publié par Compose — c'est une
deuxième barrière, pas la seule.

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

## Récupération et configuration

```bash
git clone https://github.com/rouxbarbara695-ai/KAIROS-PROJECT.git /opt/kairos
cd /opt/kairos
cp infra/.env.production.example infra/.env.production
```

Tirer les secrets au sort — jamais les inventer :

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -base64 36)"
echo "CURSOR_SECRET=$(openssl rand -base64 36)"
```

Reporter les deux lignes dans `infra/.env.production`, y renseigner
`KAIROS_DOMAIN`, puis restreindre le fichier :

```bash
chmod 600 infra/.env.production
```

## Premier démarrage

```bash
cd /opt/kairos
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml up -d --build
```

La première construction prend plusieurs minutes. Les migrations jouent dans
leur propre conteneur, qui s'arrête ensuite : c'est normal de le voir
« Exited (0) ».

Suivre l'obtention du certificat :

```bash
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml logs -f caddy
```

Puis vérifier que l'API répond derrière le domaine :

```bash
curl -si https://kairos.exemple.fr/api/v1/health | head -1
```

## Création du compte

Aucune inscription publique n'existe, et c'est délibéré : un formulaire ouvert
sur un portefeuille personnel serait une porte, pas une fonctionnalité. Le
compte se crée sur la machine, en invite masquée.

```bash
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml \
  exec api python -m app.create_user ghjuliaclara@gmail.com
```

La même commande change le mot de passe d'un compte existant, et révoque
toutes les sessions ouvertes.

Le site est alors accessible sur `https://kairos.exemple.fr`.

## Sauvegardes

Sans elles, une panne de disque efface le registre de trésorerie, les analyses
publiées et l'historique d'audit — trois choses immuables, donc sans double.

Créer la clé de chiffrement, une seule fois :

```bash
mkdir -p /etc/kairos
openssl rand -base64 48 > /etc/kairos/backup.key
chmod 600 /etc/kairos/backup.key
```

**Copier cette clé hors du serveur** (gestionnaire de mots de passe, clé USB).
Une sauvegarde chiffrée dont la clé a brûlé avec le serveur ne vaut rien.

Installer la tâche quotidienne :

```bash
chmod +x /opt/kairos/infra/scripts/*.sh
echo "17 3 * * * root /opt/kairos/infra/scripts/sauvegarde.sh >> /var/log/kairos-sauvegarde.log 2>&1" \
  > /etc/cron.d/kairos-sauvegarde
```

Le script conserve quatorze sauvegardes, et **relit** chaque fichier après
l'avoir écrit : une sauvegarde illisible est signalée le jour où elle est
produite, pas le jour où on en a besoin.

Les sauvegardes restent sur le serveur. Les copier ailleurs — c'est le point
qui sauve d'un incendie ou d'une suppression de compte :

```bash
scp root@kairos.exemple.fr:/var/backups/kairos/kairos-*.sql.gz.enc ~/sauvegardes-kairos/
```

### Essayer la restauration avant d'en avoir besoin

Une sauvegarde jamais restaurée est une hypothèse. À faire une fois, peu après
la mise en service, pendant que perdre des données n'a aucune conséquence :

```bash
/opt/kairos/infra/scripts/restauration.sh /var/backups/kairos/kairos-<horodatage>.sql.gz.enc
```

Le script arrête l'API, charge le dump dans une base neuve, puis bascule les
noms. L'ancienne base est conservée sous `kairos_precedente` jusqu'à ce que
vous la supprimiez : si la restauration s'est mal passée, rien n'est perdu.

## Mise à jour

```bash
cd /opt/kairos
git pull
docker compose --env-file infra/.env.production -f infra/docker-compose.prod.yml up -d --build
```

Les migrations jouent avant que la nouvelle API ne démarre. Faire une
sauvegarde manuelle avant une mise à jour qui touche au schéma :

```bash
/opt/kairos/infra/scripts/sauvegarde.sh
```

## Ce que la machine expose

| Service | Port public | Joignable depuis |
|---|---|---|
| Caddy | 80, 443 | Internet |
| Interface Next.js | aucun | réseau interne |
| API FastAPI | aucun | réseau interne, et `/api/*` via Caddy |
| PostgreSQL | aucun | réseau interne |
| Redis | aucun | réseau interne |

Caddy est la seule porte. `/api/*` va directement à l'API plutôt que de
traverser Next : un seul relais entre le navigateur et l'API, donc une adresse
d'origine certaine — ce dont la limitation de débit a besoin pour compter les
échecs de connexion par adresse IP plutôt que de tous les attribuer au même
relais.

Cette adresse n'est pas falsifiable : Caddy **remplace** l'en-tête
`X-Forwarded-For` par l'adresse réelle du client au lieu d'y ajouter la sienne.
Un attaquant ne peut donc pas s'inventer une nouvelle adresse à chaque essai
pour repartir d'un compteur vierge. La propriété tient tant qu'aucun
`trusted_proxies` n'est déclaré dans le Caddyfile — ne l'ajouter que le jour où
un vrai relais se place devant Caddy.

## Ce qui n'est pas fait

- **Aucune supervision.** Si un conteneur s'arrête, `restart: unless-stopped`
  le relance, mais personne n'est prévenu. Un contrôle externe gratuit
  (UptimeRobot ou équivalent) sur `https://<domaine>/api/v1/health` comble le
  manque en cinq minutes.
- **Aucun envoi de courrier.** Il n'y a ni réinitialisation de mot de passe par
  courriel ni notification : le mot de passe se change en ligne de commande sur
  le serveur.
- **Les images n'ont pas été construites en vérification.** Le fichier Compose
  de production, le Caddyfile et les scripts ont été écrits et relus, mais
  l'environnement de développement de ce dépôt ne dispose pas d'un démon
  Docker. Le premier `up -d --build` est donc aussi le premier essai réel.
