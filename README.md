# KAIROS

KAIROS est un logiciel d’aide à la décision et de pilotage pour
l’achat-revente de montres. Il évalue une **opportunité** en estimant notamment
la valeur de marché de la montre, les coûts, la rentabilité, la liquidité, le
risque et l’impact sur le portefeuille.

À partir d’une annonce ou d’une saisie manuelle, KAIROS répond à cinq questions :

1. L’objet et les données permettent-ils une analyse fiable ?
2. Quelle est la cote de marché défendable ?
3. Jusqu’à quel prix peut-on acheter ?
4. Quel profit, ROI et délai peut-on attendre ?
5. Faut-il acheter, surveiller ou abandonner ?

## Statut

**Spécifications V2 réconciliées après audit de cohérence.**

Le premier lot est volontairement manuel : créer une opportunité, confirmer
l’identité, corriger les données avec traçabilité et retrouver l’opportunité.
Les moteurs financiers viennent ensuite. Aucun collecteur réel n’est nécessaire
pour commencer.

## Principes

- KAIROS estime la montre pour décider de l’opportunité.
- Les règles sont déterministes, explicables et versionnées.
- Les résultats réels permettent de capitaliser sur l’expérience ; aucun
  apprentissage automatique n’est promis en V1.
- « Anticiper » signifie simuler les coûts, risques, délais et scénarios avant
  d’engager le capital, pas détecter automatiquement toutes les annonces.

## Documentation complète

### Gouvernance et produit

- [Instructions de développement](CLAUDE.md)
- [PRD V1 réconcilié](docs/prd/kairos-v1.md)
- [Périmètre MVP](docs/product/mvp.md)
- [Résolution des audits](docs/decisions/audit-resolution-v2.md)
- [Audit de cohérence V1 (historique, résolu)](docs/audit/coherence-audit-v1.md)
- [Questions encore ouvertes](docs/decisions/open-questions.md)

### Marque et positionnement

- [Vision](docs/business/vision.md)
- [Marque](docs/business/brand.md)
- [Principes](docs/business/principles.md)
- [Proposition de valeur](docs/business/value-proposition.md)

### Règles métier

- [Modèle métier](docs/product/domain-model.md)
- [Portes d’éligibilité](docs/product/gates.md)
- [Moteur d’analyse](docs/product/opportunity-analysis-engine.md)
- [Moteur marché](docs/product/market-engine.md)
- [Calculs](docs/product/calculation-spec.md)
- [Score](docs/product/scoring-engine.md)
- [Pricing](docs/product/pricing-strategy-engine.md)
- [Portefeuille](docs/product/portfolio-engine.md)
- [Règles des plateformes](docs/product/platform-rules.md)
- [Workflow et statuts](docs/product/workflow-and-states.md)
- [Sources et surveillance](docs/product/sources-and-monitoring.md)
- [Roadmap](docs/product/roadmap.md)

### Implémentation

- [Architecture](docs/architecture/overview.md)
- [Contrat API](docs/architecture/api-contract.md)
- [Schéma PostgreSQL](database/schema.sql)
- [Backlog V1](docs/delivery/backlog-v1.md)
- [Sprint 1](docs/delivery/sprint-01.md)
- [Plan d'implémentation KAI-001 à KAI-103](docs/delivery/implementation-plan-kai-001-103.md)
- [Stratégie de tests](docs/quality/test-strategy.md)
- [Validation technique de la V2](docs/quality/validation-v2.md)
- [Prompt de lancement Claude](PROMPT-CLAUDE.md)

## Règle de données

Chaque prix conserve sa nature, sa provenance, sa date, sa devise source et sa
conversion EUR. Une recommandation publiée est un instantané immuable : un
nouveau calcul produit une nouvelle analyse, jamais une réécriture.
