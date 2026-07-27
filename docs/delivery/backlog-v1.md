# Backlog V1 ordonné

Chaque story est livrable verticalement. Estimation indicative en points.

## Epic 0 — Socle

- **KAI-001 (3)** Monorepo web/api, Docker Compose PostgreSQL/Redis, CI.
- **KAI-002 (3)** Configuration typée, secrets, logs structurés, request IDs.
- **KAI-003 (5)** Migrations initiales et jeu de données plateformes.

Acceptation : un contributeur lance l’ensemble en une commande ; CI verte ; une
migration vierge aboutit au même schéma.

## Epic 1 — Opportunité manuelle

- **KAI-101 (5)** Créer/lister/ouvrir une opportunité.
- **KAI-102 (5)** Référence, état, set, vendeur et validation.
- **KAI-103 (3)** Détection des doublons et correction auditée.
- **KAI-104 (5)** Premier écran de saisie et fiche.

Acceptation : une Longines peut être créée sans collecteur, corrigée et
retrouvée ; valeurs inconnues préservées.

## Epic 2 — Marché

- **KAI-201 (5)** CRUD et import CSV simple de comparables.
- **KAI-202 (8)** Normalisation devise/frais/set.
- **KAI-203 (8)** pondération, anomalies et cote.
- **KAI-204 (5)** explication et confiance.

Acceptation : fixture déterministe, exclusions visibles, low≤central≤high.

## Epic 3 — Décision

- **KAI-301 (5)** stratégie et coûts.
- **KAI-302 (8)** prix maximal et scénarios.
- **KAI-303 (5)** gates.
- **KAI-304 (8)** score, plafonds et verdict.
- **KAI-305 (5)** page d’analyse explicable.

Acceptation : même entrée/même sortie ; chaque plafond testé ; aucun Acheter
au-dessus du prix maximal.

## Epic 4 — Historique et surveillance

- **KAI-401 (5)** observations append-only.
- **KAI-402 (5)** détection d’événements significatifs.
- **KAI-403 (5)** analyses versionnées et chaînées.
- **KAI-404 (5)** alertes dédupliquées.
- **KAI-405 (8)** adaptateur d’import URL sur une plateforme autorisée.

## Epic 5 — Portefeuille

- **KAI-501 (5)** transitions du pipeline.
- **KAI-502 (5)** achats et coûts prévus/réels.
- **KAI-503 (5)** mises en vente, offres, vente et encaissement.
- **KAI-504 (8)** dashboard capital/stock/performance.
- **KAI-505 (5)** prévision vs réalisé.

## Séquençage recommandé

Sprint 1 : 001–003, 101–103.  
Sprint 2 : 104, 201–204.  
Sprint 3 : 301–305.  
Sprint 4 : 401–404.  
Sprint 5 : 501–505.  
Sprint 6 : 405, stabilisation, sécurité et bêta.

Ne pas démarrer KAI-405 avant validation écrite du mode d’accès à la plateforme.
