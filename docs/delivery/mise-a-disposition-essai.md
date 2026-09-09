# Mise à disposition pour l'essai utilisateur

Ce document prépare l'essai de l'**Import assisté Catawiki** sur la machine
existante. **Rien n'est exécuté sans accord.** Les commandes sont prêtes, la
sauvegarde et le retour arrière aussi.

## Le fait qui commande tout : aucune migration

Les deux lots n'ajoutent **aucune migration**. Le schéma de la base est
strictement identique avant et après.

```bash
git diff --name-status 4b3d6ee origin/main -- infra/migrations/ database/
# A	database/schema-after-migrations.json
```

La seule ligne rendue est l'**instantané structurel** ajouté par le lot 1, lu
par un test d'intégration. Ce n'est pas une migration : il décrit la base, il
ne la modifie pas. Rien sous `infra/migrations/`.

Trois conséquences directes :

- la mise à jour est **du code seulement** ;
- le **retour arrière** consiste à redéployer le commit précédent — il n'y a
  rien à défaire en base ;
- la sauvegarde reste obligatoire, mais comme filet, pas comme condition de
  réversibilité.

## Deux chemins, et celui que je recommande

### A — Mettre à jour l'installation existante *(recommandé)*

**Pourquoi** : aucune migration, donc aucun risque de schéma ; le retour
arrière est une commande ; aucun coût, aucun accès supplémentaire.

**Ce que ça implique** : les lots d'essai atterrissent dans votre portefeuille
réel. Ils ne modifient rien de ce qui existe — l'import n'écrit que de
nouvelles opportunités — et se rangent ensuite en statut `abandoned`. Mais ils
seront visibles dans votre liste.

### B — Une seconde pile d'essai sur la même machine

**Pourquoi ce n'est pas mon choix** : Caddy occupe déjà les ports 80 et 443.
Servir un second domaine `essai.<votre-domaine>` impose de **modifier le
Caddyfile de production**. Une erreur dans ce fichier coupe le site réel — on
prendrait un risque sur la production pour éviter d'ajouter trois lignes de
test dedans.

**Coût** : un sous-domaine (gratuit si vous possédez déjà le domaine), environ
1 Go de RAM et 2 Go de disque pour la seconde base, et une trentaine de minutes
de configuration. Aucun abonnement nouveau.

Je peux le faire si vous préférez une séparation stricte. Dites-le.

## Chemin A — commandes prêtes

Toutes sont à jouer sur la machine, en `ssh root@<votre-machine>`.

### 1. Sauvegarder, et vérifier que la sauvegarde existe

```bash
/opt/kairos/infra/scripts/sauvegarde.sh
ls -lh /var/backups/kairos/ | tail -3
```

### 2. Noter le point de retour

```bash
cd /opt/kairos
git rev-parse HEAD > /root/kairos-retour-arriere.txt
cat /root/kairos-retour-arriere.txt
```

Ce fichier est le retour arrière. Sans lui, revenir demande de retrouver le
bon commit dans l'historique.

### 3. Mettre à jour

```bash
cd /opt/kairos
git fetch origin
git checkout main
git pull
docker compose --env-file infra/.env.production \
  -f infra/docker-compose.prod.yml up -d --build
```

### 4. Vérifier que ça tourne

```bash
docker compose --env-file infra/.env.production \
  -f infra/docker-compose.prod.yml ps
curl -sf https://<votre-domaine>/api/v1/health && echo " — API vivante"
```

Les quatre services (`postgres`, `redis`, `api`, `web`, `caddy`) doivent être
`running`, et `migrate` `exited (0)`.

### 5. Retour arrière, si besoin

```bash
cd /opt/kairos
git checkout "$(cat /root/kairos-retour-arriere.txt)"
docker compose --env-file infra/.env.production \
  -f infra/docker-compose.prod.yml up -d --build
```

**Aucune restauration de base n'est nécessaire** : le schéma n'a pas changé.
Les opportunités créées pendant l'essai resteront, et se rangent en
`abandoned`.

Si vous voulez malgré tout revenir à l'état d'avant :

```bash
/opt/kairos/infra/scripts/restauration.sh /var/backups/kairos/<fichier>.sql.gz.enc
```

## Coûts et accès supplémentaires

| | |
|---|---|
| Coût | **aucun** pour le chemin A |
| Accès | **aucun** nouveau — le `ssh` existant suffit |
| Temps d'indisponibilité | environ 1 à 2 minutes, le temps de la reconstruction |
| Chemin B | un sous-domaine, ~1 Go de RAM, ~30 min de configuration |

## Ordre de fusion, et le piège à éviter — fait le 9 septembre 2026

L'ordre était **#22 puis #23**. Les deux sont fusionnées.

### Ce qui s'est réellement passé, et qui contredit ce que ce document annonçait

Ce document affirmait que GitHub **rebasculerait automatiquement** la cible de
`#23` sur `main` après la fusion de `#22`. **C'est faux, et vérifié comme tel** :
après la fusion de `#22`, `#23` pointait toujours sur
`claude/lot1-securisation-donnees`. GitHub ne redirige la cible que lorsque la
branche de base est **supprimée**, ce qui n'était pas le cas. La cible a donc
été portée sur `main` par une action explicite.

La leçon reste celle qui était visée, et elle est renforcée : **un changement
de cible n'est pas un rebase**, et il ne faut pas davantage supposer qu'il a
lieu.

### La méthode de fusion compte autant que l'ordre

Le dépôt fusionne par **commit de fusion**, pas par écrasement. Ce détail est
décisif quand une branche est empilée sur une autre :

- par commit de fusion, la tête du lot 1 (`b576f9d`) **reste un ancêtre** de
  `main`. La base de fusion de `main` et du lot 2 est donc exactement
  `b576f9d`, et le diff du lot 2 ne contient que le lot 2 ;
- par écrasement, `main` aurait reçu un commit neuf sans lien de parenté, la
  base de fusion serait retombée sur `4b3d6ee` — d'avant les deux lots — et le
  diff du lot 2 aurait réaffiché tout le lot 1, avec les conflits que cela
  suppose. Il aurait alors fallu **rebaser** la branche du lot 2.

### Les vérifications à rejouer, et ce qu'elles ont donné

```bash
git fetch origin
git merge-base --is-ancestor b576f9d origin/main   # tête du lot 1 dans main ?
git merge-base origin/main origin/claude/lot2-prefill-annonce
git log --oneline origin/main..origin/claude/lot2-prefill-annonce
git diff --stat origin/main...origin/claude/lot2-prefill-annonce
```

| Vérification | Résultat constaté |
|---|---|
| `b576f9d` ancêtre de `main` | oui — aucun rebase nécessaire |
| base de fusion `main` / lot 2 | `b576f9d` |
| commits du lot 2 par rapport à `main` | 5, tous du lot 2 |
| diff avant / après changement de cible | **identique** : 52 fichiers, +9106/−106 |
| fichiers du lot 1 dans le diff du lot 2 | aucun |

Le diff resté identique de part et d'autre du changement de cible est la preuve
recherchée : aucun contenu du lot 1 n'est revenu dans le lot 2.

### Après fusion

`main` est à `2339458`. Son arbre est **identique** à celui de `21a3a48`, le
commit sur lequel les sept contrôles sont passés : le contenu déployé est donc
exactement le contenu testé, et non un assemblage jamais éprouvé.

Le point de retour arrière d'avant les deux lots est `4b3d6ee`.
