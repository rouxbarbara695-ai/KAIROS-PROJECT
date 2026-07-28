# Portes d’éligibilité

Les codes ci-dessous sont des identifiants publics stables. Ne jamais recycler
un code pour un autre sens.

| Code | Passe si | Échec | Résultat |
|---|---|---|---|
| `G1_AUTHENTICITY` | aucun signal majeur non résolu | contrefaçon probable, provenance incompatible, composants rendant l’identité douteuse | `pass`, expertise requise |
| `G2_IDENTIFICATION` | `passed` si référence `confirmed|corrected`; `passed_with_warning` si suggestion ≥80 | référence inconnue/ambiguë ou suggestion <80 | `analysis_impossible` |
| `G3_DATA_QUALITY` | prix, devise, état, set et pays exploitables | donnée indispensable absente sans borne prudente | `analysis_impossible` |
| `G4_MARKET_SUPPORT` | ≥2 comparables recevables, poids total >0 | marché non documenté | `analysis_impossible` |
| `G5_SELLER_RISK` | risque faible/moyen avec contrôles suffisants | fraude probable, paiement/livraison incompatibles avec la stratégie | `pass` |

## Statuts sérialisés

- `passed`
- `passed_with_warning`
- `failed`
- `not_evaluated`

Chaque résultat conserve `code`, `status`, `reason_codes[]`, `evidence_ids[]` et
`evaluated_at`. Après le premier échec bloquant, les portes suivantes peuvent
être `not_evaluated`, mais les échecs déjà connus restent visibles.

## Règles

- Une porte n’ajoute aucun point au score.
- Une marge élevée ne compense jamais un échec.
- Une modification non originale affecte le pilier État ; elle n’échoue
  `G1_AUTHENTICITY` que si elle empêche une identification/authenticité
  raisonnable.
- Un risque vendeur moyen peut passer avec avertissement et plafonner le verdict
  à `watch` selon le ruleset.
