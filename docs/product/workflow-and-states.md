# Workflow, statuts et transitions

## Statuts d’opportunité

| Statut | Sens | Transitions autorisées |
|---|---|---|
| `watching` | en veille ou analyse en cours | buy, auction, abandoned |
| `buy` | décision d’achat, action non finalisée | purchased, watching, abandoned |
| `auction` | enchère active | purchased, watching, abandoned |
| `purchased` | achat confirmé, paiement dû/effectué | in_stock |
| `in_stock` | montre reçue, non publiée | listed_for_sale |
| `listed_for_sale` | proposée à la vente | awaiting_buyer_payment, in_stock |
| `awaiting_buyer_payment` | acheteur engagé, paiement en cours | awaiting_payout, listed_for_sale |
| `awaiting_payout` | remise/livraison faite, fonds retenus | sold, listed_for_sale |
| `sold` | fonds reçus, opération clôturable | terminal |
| `abandoned` | opportunité refusée/expirée | watching uniquement via réouverture |

Toute transition crée un événement avec auteur, date, ancien/nouveau statut,
motif et données financières pertinentes. Un retour en arrière n’efface rien.

## Invariants

- `purchased` exige prix, date, devise et plateforme/canal.
- `in_stock` exige réception confirmée.
- `listed_for_sale` exige au moins un canal et prix demandé.
- `awaiting_payout` exige une vente et un mode de remise/livraison.
- `sold` exige prix réalisé, frais réels et date d’encaissement.
- une opportunité abandonnée conserve analyses, observations et motif.

## Événements déclenchant un recalcul

- prix demandé modifié d’au moins 1 % ou 10 € ;
- nouvelle règle de frais applicable à une opération non clôturée ;
- comparable ajouté, corrigé ou exclu ;
- référence, état, set, pays ou vendeur corrigé ;
- taux de change expiré ;
- capital disponible ou stratégie modifiés ;
- statut d’annonce ou fin d’enchère ;
- recalcul manuel.

## Politique d’alertes

Créer une alerte si : verdict change ; prix passe sous le prix maximal ; enchère
se termine dans 24 h puis 3 h ; prix baisse d’au moins 5 % ; annonce disparaît ;
confiance baisse sous 60 ; opération reste 30 jours sans offre ; paiement ou
encaissement dépasse l’échéance.

Dédupliquer par `opportunity + alert_type + analysis_id`. Les collectes
identiques ne créent rien. Regrouper les événements non critiques de même type.
