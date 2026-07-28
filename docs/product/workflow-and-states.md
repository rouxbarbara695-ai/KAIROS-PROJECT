# Workflow, statuts et transitions

## Statuts

| Statut | Sens | Transitions |
|---|---|---|
| `watching` | analyse/veille manuelle | `buy`, `auction`, `abandoned` |
| `buy` | intention d’achat | `purchased`, `watching`, `abandoned` |
| `auction` | enchère active | `purchased`, `watching`, `abandoned` |
| `purchased` | achat confirmé | `in_stock` |
| `in_stock` | reçu, non publié | `listed_for_sale` |
| `listed_for_sale` | en vente | `awaiting_buyer_payment`, `in_stock` |
| `awaiting_buyer_payment` | engagement acheteur | `awaiting_payout`, `listed_for_sale` |
| `awaiting_payout` | livré/remis, fonds retenus | `sold`, `listed_for_sale` |
| `sold` | encaissement reçu | terminal |
| `abandoned` | refusée/expirée | `watching` via réouverture motivée |

Chaque transition crée un `opportunity_event` et un `audit_event`, tous deux
append-only.

## Invariants

- `purchased` : achat, devise, conversion EUR et date.
- `in_stock` : réception confirmée.
- `listed_for_sale` : canal et prix demandé.
- `awaiting_payout` : vente et mode de livraison/remise.
- `sold` : prix réalisé, coûts réels et date d’encaissement.
- une réouverture conserve tout l’historique.

## Recalcul

Déclencheurs :

- prix modifié d’au moins `max(1 %, 10 €)` ;
- comparable ajouté, corrigé, exclu ou réintégré ;
- référence, état, set, pays ou vendeur corrigé ;
- nouvelle version de règle choisie pour une opération ouverte ;
- taux FX expiré ;
- capital ou stratégie modifiés ;
- enchère terminée ou statut changé ;
- demande manuelle.

Le recalcul crée une analyse enfant. Une contrainte unique interdit deux enfants
directs du même parent.

## Alertes

- verdict modifié ;
- prix franchissant le maximum prudent ;
- fin d’enchère à 24 h puis 3 h ;
- baisse ≥5 % ;
- disparition d’annonce ;
- `valuation_confidence` franchissant 60 ;
- 30 jours sans offre qualifiée ;
- paiement/encaissement en retard.

Clé de déduplication :
`portfolio_id + opportunity_id + alert_type + coalesce(analysis_id, event_id)`.
Une alerte ne peut être recréée avec la même clé.
