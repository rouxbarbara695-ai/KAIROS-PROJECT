# Architecture technique

## Décision

KAIROS démarre comme un **monolithe modulaire** : une application déployable
simplement, composée de domaines séparés et testables.

| Couche | Choix cible | Responsabilité |
|---|---|---|
| Interface | Next.js / React | Parcours utilisateur et dashboard |
| API | FastAPI / Python | Règles métier et orchestration |
| Données | PostgreSQL | État courant, relations et historiques |
| Tâches | Redis + workers | Collecte, recalculs et alertes |
| Fichiers | Stockage objet S3 | Photos et documents |

## Modules

- `identity` : références et fiabilité d’identification ;
- `market` : comparables et valorisations ;
- `pricing` : coûts, marges et prix maximal ;
- `scoring` : piliers, règles de dépendance et verdict ;
- `monitoring` : collecteurs, observations et événements ;
- `portfolio` : capital, stock, achats et ventes ;
- `notifications` : seuils et livraison des alertes ;
- `platforms` : règles versionnées propres aux plateformes.

## Flux principal

1. Une annonce est soumise.
2. Un collecteur ou la saisie manuelle crée une observation normalisée.
3. L’identification et les portes d’éligibilité sont évaluées.
4. Les comparables produisent une valorisation versionnée.
5. Le pricing et le scoring produisent une analyse immuable.
6. Une nouvelle observation significative déclenche une nouvelle analyse.
7. Une alerte est créée seulement si un seuil utile est franchi.

## Contraintes

- les calculs métier ne vivent pas uniquement dans l’interface ;
- une analyse passée n’est jamais écrasée ;
- chaque donnée externe conserve sa provenance et sa fraîcheur ;
- la panne d’un collecteur ne bloque pas les autres sources ;
- la saisie manuelle reste disponible ;
- les secrets sont fournis par variables d’environnement et jamais versionnés.

## Arborescence de code recommandée

```text
apps/api/app/
  identity/ market/ pricing/ scoring/ monitoring/ portfolio/ platforms/
  shared/domain/ shared/infrastructure/
apps/web/src/
  app/ components/ features/ lib/
packages/contracts/
infra/migrations/ infra/docker/
```

Chaque module API sépare `domain`, `application`, `ports` et `adapters`.
L’orchestrateur d’analyse appelle les moteurs dans l’ordre : gates,
valorisation, pricing, portefeuille, scoring, verdict, persistance. La
transaction publie l’analyse complète ou rien ; les collectes restent
asynchrones et idempotentes.

## Sécurité et exploitation

- authentification requise hors environnement local ;
- filtrage de toutes les ressources par portefeuille ;
- validation stricte des URL et protection SSRF lors des imports ;
- limites de taille, délais et types MIME pour les fichiers ;
- logs JSON avec `request_id`, `job_id`, `opportunity_id`, sans token ;
- métriques : latence, taux d’erreur, âge des données, jobs en retard ;
- sauvegarde PostgreSQL quotidienne et test de restauration trimestriel ;
- endpoint de santé séparant disponibilité API et dépendances.

## Déploiement

Trois environnements : local, staging, production. Une image API, une image web
et la même image API lancée en worker. Les migrations sont exécutées une seule
fois avant bascule. Aucun déploiement production si les migrations, fixtures
financières ou contrats OpenAPI échouent.
