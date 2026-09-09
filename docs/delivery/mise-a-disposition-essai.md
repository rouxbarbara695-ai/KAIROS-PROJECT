# Mise à disposition pour l'essai utilisateur

Ce document prépare l'essai de l'**Import assisté Catawiki** sur la machine
existante. **Rien n'est exécuté sans accord.** Les commandes sont prêtes, la
sauvegarde et le retour arrière aussi.

## Le fait qui commande tout : aucune migration

Les deux lots n'ajoutent **aucune migration**. Le schéma de la base est
strictement identique avant et après.

```bash
git diff --name-status origin/main...HEAD -- infra/migrations/
# (aucune sortie)
```

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

## Ordre de fusion, et le piège à éviter

L'ordre est **#22 puis #23**.

`#23` est basée sur la branche de `#22`. Quand `#22` sera fusionnée, GitHub
**rebasculera automatiquement la cible de #23 sur `main`**. Ce changement de
cible n'est **pas** un rebase : les commits de `#23` restent posés sur
l'ancienne base. Le diff affiché redevient correct parce que les commits de
`#22` sont désormais dans `main`, mais il faut le **vérifier**, pas le
supposer :

```bash
git fetch origin
git log --oneline origin/main..origin/claude/lot2-prefill-annonce
# doit ne lister que les commits du lot 2
git diff --stat origin/main...origin/claude/lot2-prefill-annonce
# ne doit plus contenir les fichiers du lot 1
```

Si le diff contient encore du lot 1, c'est que `#22` n'est pas fusionnée, ou
que la branche du lot 2 doit être mise à jour depuis `main`.
