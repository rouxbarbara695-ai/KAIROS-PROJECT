# Moteur portefeuille

Le moteur portefeuille calcule l’impact d’une opportunité à partir d’un grand
livre append-only.

## Trésorerie

```text
capital_disponible =
  somme(apports + encaissements + ajustements_positifs)
  - somme(retraits + paiements + coûts_réels + ajustements_négatifs)
```

Chaque écriture conserve montant source, montant EUR, taux, date, auteur,
catégorie et lien éventuel vers l’opportunité.

## Positions

- `engagé` : décision d’achat ou enchère non réglée ;
- `immobilisé` : acquisition et coûts réels des montres non vendues ;
- `en_attente_encaissement` : produit net vendu mais non reçu ;
- `disponible` : trésorerie immédiatement mobilisable.

## Indicateurs

- allocation après achat = coût d’acquisition prudent / capital disponible ;
- concentration par marque = coût immobilisé de la marque / stock total ;
- immobilisation = capital immobilisé / capital de référence ;
- profit réalisé = encaissement net − coûts réels ;
- écart prévision/réalisé pour profit, ROI et durée.

Les points de score utilisent les valeurs juste avant la décision et un snapshot
est conservé dans l’analyse.
