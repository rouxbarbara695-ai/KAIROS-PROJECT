# KAIROS

KAIROS est un logiciel d’aide à la décision et de pilotage conçu pour
l’achat-revente de montres.

À partir d’une annonce, KAIROS doit répondre à cinq questions :

1. La montre est-elle correctement identifiée et analysable ?
2. Quelle est sa valeur de marché défendable ?
3. Jusqu’à quel prix peut-on l’acheter ?
4. Quelle rentabilité et quel délai de revente peut-on attendre ?
5. Faut-il acheter, surveiller ou abandonner ?

Le produit suivra ensuite l’opération jusqu’à la vente réelle afin de comparer
les prévisions aux résultats et d’améliorer progressivement ses recommandations.

## Statut

**Spécifications V1 prêtes pour implémentation progressive.**

Le premier parcours à construire est :

> Ajouter une annonce → l’identifier → ajouter des comparables → produire une
> cote → calculer le prix maximal → historiser les observations → recalculer
> l’analyse → générer une alerte.

## Architecture cible

- application web responsive en Next.js / React ;
- API métier Python avec FastAPI ;
- base PostgreSQL ;
- traitements planifiés avec une file de tâches adossée à Redis ;
- collecteurs indépendants par plateforme ;
- stockage objet pour les photos et documents ;
- monolithe modulaire pour la première version.

## Documentation

- [Vision](docs/business/vision.md)
- [Instructions pour Claude](CLAUDE.md)
- [PRD complet V1](docs/prd/kairos-v1.md)
- [Proposition de valeur](docs/business/value-proposition.md)
- [Périmètre MVP](docs/product/mvp.md)
- [Modèle métier](docs/product/domain-model.md)
- [Calculs métier](docs/product/calculation-spec.md)
- [Règles des plateformes](docs/product/platform-rules.md)
- [Workflow et statuts](docs/product/workflow-and-states.md)
- [Architecture technique](docs/architecture/overview.md)
- [Contrat API](docs/architecture/api-contract.md)
- [Sources et surveillance](docs/product/sources-and-monitoring.md)
- [Schéma initial de la base](database/schema.sql)
- [Sprint 1](docs/delivery/sprint-01.md)
- [Backlog V1](docs/delivery/backlog-v1.md)
- [Stratégie de tests](docs/quality/test-strategy.md)
- [Décisions ouvertes](docs/decisions/open-questions.md)
- [Roadmap](docs/product/roadmap.md)

## Règle de produit

KAIROS distingue toujours :

- un prix demandé ;
- un prix réellement réalisé ;
- une estimation externe ;
- une estimation produite par KAIROS.

Chaque donnée conserve sa provenance, sa date, sa devise et son niveau de
confiance. Une recommandation doit rester compréhensible et vérifiable.
