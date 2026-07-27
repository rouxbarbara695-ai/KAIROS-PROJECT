# Instructions de développement — KAIROS

Ce dépôt contient le contrat fonctionnel de KAIROS. Claude doit lire, dans cet
ordre : `README.md`, `docs/prd/kairos-v1.md`, `docs/product/calculation-spec.md`,
`docs/product/platform-rules.md`, `docs/architecture/api-contract.md`,
`docs/architecture/overview.md`, `docs/delivery/backlog-v1.md`,
`docs/quality/test-strategy.md`.

## Règles non négociables

1. Ne jamais inventer une règle métier absente. Créer une entrée dans
   `docs/decisions/open-questions.md` et choisir une valeur configurable.
2. Utiliser des `Decimal`, jamais des flottants, pour les montants et taux.
3. Stocker les montants dans leur devise source et leur équivalent EUR avec le
   taux et l’horodatage utilisés.
4. Une analyse publiée est immuable. Un recalcul crée une nouvelle version.
5. Distinguer prix demandé, prix réalisé, estimation externe et estimation
   KAIROS dans la base, l’API et l’interface.
6. Toute recommandation expose ses données, règles, exclusions et calculs.
7. Un échec de collecte ne doit ni effacer une observation valide ni transformer
   une annonce en annonce vendue.
8. La saisie manuelle doit fonctionner même si aucun collecteur externe ne
   fonctionne.
9. Aucun scraping réel ne doit être ajouté sans validation des conditions
   d’utilisation, du mode d’accès et de la fréquence.
10. Chaque règle chiffrée porte un `rules_version`.

## Architecture attendue

Monorepo :

```text
apps/web/                 Next.js, TypeScript
apps/api/                 FastAPI, Python
packages/contracts/       schémas OpenAPI générés / types partagés
infra/                    Docker Compose, migrations, CI
tests/fixtures/           cas métier reproductibles
docs/                     source de vérité fonctionnelle
```

Le MVP est un monolithe modulaire. Ne pas introduire de microservices. Les
modules métier ne dépendent pas de FastAPI : ils acceptent des objets typés et
retournent des résultats déterministes. Les adaptateurs HTTP, PostgreSQL, file
de tâches et collecteurs restent en périphérie.

## Definition of Done

Une story n’est terminée que si :

- migration, modèle et contrat API sont cohérents ;
- tests unitaires et d’intégration couvrent le nominal et les limites ;
- les calculs sont reproductibles avec les fixtures ;
- les erreurs utilisent le catalogue documenté ;
- les logs n’exposent aucun secret ni donnée inutile ;
- la documentation concernée est mise à jour ;
- formatage, typage, lint et tests passent en CI.

## Priorité de réalisation

Construire d’abord le parcours manuel complet, puis l’import URL assisté, puis
la surveillance. Ne pas commencer par le scraping, le machine learning,
l’abonnement ou une application mobile.
