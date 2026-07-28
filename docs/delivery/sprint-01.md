# Sprint 1 — Socle et opportunité manuelle

## Périmètre

Uniquement **KAI-001, KAI-002, KAI-003, KAI-101, KAI-102 et KAI-103**.

## Objectif

Créer une Longines manuellement, sans annonce ni collecteur, confirmer sa
référence, corriger état/set/vendeur avec audit, la retrouver et détecter un
doublon.

## Livrables

1. Monorepo, local, CI et configuration.
2. Migration du schéma V2 et seeds.
3. Modèles, repositories et contrôle de portefeuille.
4. `POST/GET /opportunities`.
5. Confirmation de référence.
6. Corrections dédiées, `If-Match` et événements d’audit.
7. Déduplication des trois clés.
8. Tests unitaires, intégration PostgreSQL et API.

## Critères d’acceptation

- mode manuel valide sans `listing_id` ni URL ;
- `manual_identifier` unique par portefeuille ;
- confirmation trace auteur/date/statut ;
- montant EUR conserve taux 1 et horodatage ;
- correction n’écrase pas la preuve brute ;
- audit event non modifiable ;
- ressource d’un autre portefeuille renvoie 404 ;
- concurrence obsolète et idempotence produisent les erreurs documentées ;
- migration base vide et seeds sont déterministes.

## Non inclus

Comparables, valorisation, pricing, score, alertes, portefeuille financier,
interface complète et tout accès automatisé.
