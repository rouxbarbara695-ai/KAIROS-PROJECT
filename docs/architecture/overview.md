# Architecture technique

## Décision

KAIROS V1 est un monolithe modulaire horloger et mono-organisation. Les limites
entre domaines sont explicites, mais une seule API et un seul schéma sont
déployés.

| Couche | Choix | Responsabilité |
|---|---|---|
| Web | Next.js / TypeScript | formulaires, analyse, portefeuille |
| API | FastAPI / Python | orchestration et contrats |
| Domaine | Python pur | règles et calculs déterministes |
| Données | PostgreSQL | contraintes, historiques, audit |
| Jobs | Redis + worker | imports autorisés, recalculs, alertes |
| Fichiers | interface S3 | pièces justificatives futures |

## Modules

- `identity` : montres, références, confirmation ;
- `opportunities` : saisie, déduplication, corrections ;
- `market` : comparables et valorisations ;
- `pricing` : coûts, scénarios et prix maximal ;
- `scoring` : portes, piliers, caps et verdict ;
- `portfolio` : grand livre, stock, achats et ventes ;
- `monitoring` : observations et jobs autorisés ;
- `platforms` : règles versionnées et garde de conformité ;
- `audit` : événements append-only ;
- `notifications` : alertes dédupliquées ;
- `telemetry` : KPI produit sans données sensibles.

## Flux transactionnel

1. La commande est authentifiée et filtrée par portefeuille.
2. Le service d’application charge des snapshots immuables.
3. Les moteurs purs calculent portes, valorisation, pricing, portefeuille,
   score et verdict.
4. Une transaction écrit traces et analyse brouillon.
5. La publication fixe `published_at`; la base interdit ensuite update/delete.
6. Les événements post-commit déclenchent métriques ou alertes.

Une porte bloquante autorise une analyse publiée sans valorisation, score ou
montants.

## Arborescence

```text
apps/api/app/
  identity/ opportunities/ market/ pricing/ scoring/
  portfolio/ monitoring/ platforms/ audit/ notifications/ telemetry/
  shared/domain/ shared/application/ shared/infrastructure/
apps/web/src/
  app/ components/ features/ lib/
packages/contracts/
infra/migrations/ infra/docker/
tests/fixtures/ tests/unit/ tests/integration/ tests/contract/
```

Chaque module sépare `domain`, `application`, `ports`, `adapters`. Aucun moteur
du domaine n’importe FastAPI, SQLAlchemy ou Redis.

## Cohérence, concurrence et idempotence

- `version` et `If-Match` protègent les ressources modifiables.
- `Idempotency-Key` protège commandes financières, créations et jobs.
- Les chaînes d’analyses et de corrections sont linéaires par contraintes
  uniques.
- Les règles et stratégies sont épinglées par identifiant et snapshot.
- Les écritures append-only ne sont corrigées que par événements compensatoires.

## Sécurité

- authentification requise hors local ;
- `portfolio_id` obligatoire et vérifié partout ;
- URL validée, DNS/IP privés bloqués, redirections limitées ;
- numéros de série chiffrés et absents des DTO généraux ;
- secrets par environnement ;
- logs JSON avec identifiants techniques, sans tokens ni contenu brut ;
- télémétrie avec liste blanche de propriétés ;
- sauvegarde quotidienne et restauration trimestrielle.

## Exploitation

Métriques techniques : latence, erreurs, connexions DB, jobs en retard, âge des
FX et taux d’échec. KPI produit : durée de parcours, publication d’analyse,
action après alerte et clôture prévision/réalisé.

Environnements local, staging et production. Aucune mise en production si
migrations base vide, fixtures financières, OpenAPI ou tests d’immuabilité
échouent.
