# Backlog V1 ordonné

## Epic 0 — Socle

- **KAI-001 (3)** Monorepo web/API, Docker Compose PostgreSQL/Redis, CI.
- **KAI-002 (3)** Configuration typée, secrets, logs, request IDs.
- **KAI-003 (8)** Migrations V2, contraintes, triggers d’immuabilité, seeds
  plateformes et ruleset.

Acceptation : installation en une commande ; base vide migrée ; seeds
reproductibles ; tests SQL d’immutabilité et d’isolation verts.

## Epic 1 — Opportunité manuelle

- **KAI-101 (5)** Créer, lister et ouvrir une opportunité manuelle.
- **KAI-102 (5)** Confirmer/corriger/inconnue la référence ; état, set, vendeur.
- **KAI-103 (5)** Déduplication et journal de correction append-only.
- **KAI-104 (5)** Écran de saisie et fiche.

Acceptation : Longines créée sans annonce ni collecteur, EUR correctement
stocké, correction auditable, doublons manuel/URL/externe refusés.

## Epic 2 — Marché

- **KAI-201 (5)** Comparables manuels, overrides et import CSV.
- **KAI-202 (8)** FX, coût acheteur et ajustement de set.
- **KAI-203 (8)** poids, anomalies, percentiles et valorisation immuable.
- **KAI-204 (5)** `valuation_confidence` et trace de calcul.

## Epic 3 — Décision

- **KAI-301 (5)** rulesets, stratégies versionnées et coûts par scénarios.
- **KAI-302 (8)** pricing, maximum prudent et délai.
- **KAI-303 (5)** cinq portes stables.
- **KAI-304 (8)** cinq piliers, caps et verdict.
- **KAI-305 (5)** écran d’analyse explicable.

## Epic 4 — Historique

- **KAI-401 (5)** observations et prix append-only.
- **KAI-402 (5)** événements significatifs.
- **KAI-403 (5)** analyses chaînées et publication immuable.
- **KAI-404 (5)** alertes dédupliquées.
- **KAI-405 (8)** un adaptateur d’import autorisé.

KAI-405 est conditionnel à une décision écrite ; il ne bloque pas la V1 manuelle.

## Epic 5 — Portefeuille

- **KAI-501 (5)** transitions.
- **KAI-502 (8)** grand livre, achats et coûts.
- **KAI-503 (5)** mise en vente, vente et encaissement.
- **KAI-504 (8)** dashboard réconcilié.
- **KAI-505 (5)** prévision/réalisé et revue des règles.

## Séquençage

| Sprint | Stories |
|---|---|
| 1 | KAI-001 à KAI-103 |
| 2 | KAI-104, KAI-201 à KAI-204 |
| 3 | KAI-301 à KAI-305 |
| 4 | KAI-401 à KAI-404 |
| 5 | KAI-501 à KAI-505 |
| 6 conditionnel | KAI-405, sécurité et bêta |
