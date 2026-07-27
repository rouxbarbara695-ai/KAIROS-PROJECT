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
