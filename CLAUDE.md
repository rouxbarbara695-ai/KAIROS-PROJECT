# Instructions de développement — KAIROS

Ce dépôt est le contrat fonctionnel et technique de KAIROS. La documentation
est en français et la graphie canonique est toujours **KAIROS**.

## Ordre de lecture obligatoire

Avant tout code, lire intégralement :

1. `README.md`
2. `docs/prd/kairos-v1.md`
3. `docs/decisions/audit-resolution-v2.md`
4. `docs/decisions/open-questions.md`
5. `docs/product/domain-model.md`
6. `docs/product/gates.md`
7. `docs/product/calculation-spec.md`
8. `docs/product/scoring-engine.md`
9. `docs/product/platform-rules.md`
10. `docs/product/workflow-and-states.md`
11. `docs/architecture/api-contract.md`
12. `docs/architecture/overview.md`
13. `database/schema.sql`
14. `docs/delivery/backlog-v1.md`
15. `docs/delivery/sprint-01.md`
16. `docs/quality/test-strategy.md`

Les autres documents apportent le contexte produit et commercial. Ils ne
peuvent pas contredire cette hiérarchie.

## Hiérarchie des sources de vérité

| Sujet | Source faisant foi |
|---|---|
| Périmètre, utilisateurs, parcours, exigences | PRD |
| Arbitrages déjà adoptés et sujets encore ouverts | décisions |
| Formules, barèmes et arrondis | `calculation-spec.md` |
| Portes, score, verdict et transitions | fichiers produit dédiés |
| Représentation échangée | contrat API |
| Persistance et contraintes | schéma SQL |
| Ordre de livraison | backlog et sprint |

Si deux sources de même niveau se contredisent, ne pas choisir silencieusement :
documenter l’écart et arrêter le lot concerné.

## Règles non négociables

1. Ne jamais inventer une règle métier. Une valeur provisoire doit être
   configurable, versionnée et signalée dans `open-questions.md`.
2. Utiliser `Decimal`, jamais des flottants, pour montants, taux et scores.
3. Pour tout montant externe ou transactionnel, conserver devise source,
   montant EUR, taux de conversion, sens du taux, source et horodatage.
4. Une analyse publiée, une valorisation, une observation et un événement
   d’audit sont immuables. Un recalcul crée une nouvelle version.
5. Distinguer prix demandé, enchère courante, prix marteau, prix réalisé,
   estimation externe et estimation KAIROS.
6. Toute recommandation expose ses entrées, règles, versions, exclusions,
   ajustements, calculs, plafonds et motifs.
7. Un échec de collecte n’efface aucune donnée valide et ne prouve jamais une
   vente.
8. Le parcours manuel complet fonctionne sans collecteur externe.
9. Aucun accès automatisé à une plateforme n’est activé sans validation écrite
   du mode d’accès, des conditions d’utilisation et de la fréquence.
10. Chaque règle chiffrée appartient à un `ruleset` immuable et versionné.
11. Les numéros de série sont privés : jamais dans les URL, logs, analytics ou
    réponses API générales.
12. Le MVP est horloger et mono-organisation. Ne pas généraliser prématurément
    à d’autres objets, au SaaS multi-tenant ou au machine learning.

## Architecture attendue

```text
apps/web/                 Next.js, TypeScript
apps/api/                 FastAPI, Python
packages/contracts/       OpenAPI généré et types partagés
infra/                    Docker Compose, migrations, CI
tests/fixtures/           cas métier reproductibles
docs/                     contrat fonctionnel
```

Le MVP est un monolithe modulaire. Les moteurs métier sont des fonctions pures
et déterministes, indépendantes de FastAPI et de PostgreSQL. Les adaptateurs
HTTP, base, tâches et plateformes restent en périphérie.

## Definition of Done

Une story est terminée uniquement si :

- migration, domaine, API et documentation sont cohérents ;
- tests unitaires, d’intégration et de contrat couvrent nominal et limites ;
- migrations `up` depuis une base vide et contraintes SQL sont vérifiées ;
- calculs et arrondis reproduisent exactement les fixtures ;
- erreurs et conflits utilisent le catalogue API ;
- aucune donnée sensible ou secret n’apparaît dans logs et réponses ;
- formatage, typage, lint, tests et détection de secrets passent en CI.

## Ordre de réalisation

Construire d’abord KAI-001 à KAI-103 : socle et opportunité manuelle. Puis
marché, décision, historique, portefeuille. La surveillance automatisée
KAI-405 reste conditionnelle et n’appartient pas au premier MVP manuel.
