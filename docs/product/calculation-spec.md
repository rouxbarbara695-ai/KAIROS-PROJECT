# Spécification des calculs métier

Toutes les valeurs sont calculées en `Decimal`. Les taux sont exprimés en
décimal (`0.065` = 6,5 %). Les résultats monétaires sont arrondis à 2 décimales
uniquement en sortie, avec `ROUND_HALF_UP`.

## 1. Normalisation d’un comparable

### Prix rendu comparable

```text
price_eur = source_price × fx_rate_at_observation
net_market_price =
  price_eur
  - seller_fee_included_if_known
  + buyer_fee_if_not_included
  + compulsory_shipping
```

Le prix affiché à l’utilisateur reste le prix source. `net_market_price` sert au
calcul et doit exposer ses composants.

### Facteurs de poids

```text
weight = confidence × recency × reference × condition × completeness
         × seller_independence × source_quality
```

| Facteur | Valeur initiale |
|---|---:|
| Niveau A / B / C / D / E | 1,00 / 0,85 / 0,65 / 0,40 / 0,15 |
| âge ≤30 j / 31–90 / 91–180 / 181–365 / >365 | 1,00 / 0,90 / 0,75 / 0,55 / 0,35 |
| même référence / variante très proche / référence différente | 1,00 / 0,60 / exclu |
| état à ±1 niveau / ±2 / inconnu | 1,00 / 0,70 / 0,50 |
| set identique / un élément d’écart / inconnu | 1,00 / 0,80 / 0,60 |
| vendeur unique / doublon probable | 1,00 / 0,20 |
| vente confirmée / marchand reconnu / annonce P2P | 1,00 / 0,85 / 0,65 |

Les coefficients sont configurables et versionnés.

### Ajustement set

À défaut de comparables suffisants strictement identiques :

- boîte **ou** papiers : +10 % par rapport à “watch only” ;
- boîte **et** papiers : +20 % ;
- ne pas cumuler au-delà de +20 % ;
- accessoires ordinaires : 0 % par défaut ;
- accessoire rare : ajustement manuel justifié.

L’ajustement est appliqué au comparable pour le ramener au set de la montre
cible, puis journalisé.

### Anomalies

Calculer médiane `M` et MAD. Un comparable est signalé si
`abs(price-M)/(1.4826×MAD) > 3.5`. Si MAD=0, utiliser IQR. Il n’est jamais
supprimé ; il est exclu automatiquement avec motif, réintégrable manuellement.

## 2. Cote de marché

Préconditions : au moins 2 comparables recevables et somme des poids > 0.

```text
central = weighted_median(adjusted_price, weight)
low     = weighted_percentile(25)
high    = weighted_percentile(75)
```

Avec moins de 5 comparables, élargir l’intervalle :

```text
low  = min(low, central × 0.90)
high = max(high, central × 1.10)
```

### Confiance de valorisation /100

```text
confidence =
  30% volume
  + 25% source_quality
  + 20% recency
  + 15% similarity
  + 10% dispersion
```

Barèmes :

- volume : 2=30, 3=50, 4=65, 5–7=80, ≥8=100 ;
- source : moyenne pondérée des niveaux A=100, B=85, C=65, D=40, E=15 ;
- récence : moyenne des facteurs de récence ×100 ;
- similarité : moyenne de `reference×condition×completeness` ×100 ;
- dispersion : 100 si `(high-low)/central≤10 %`, 80 si ≤20 %, 60 si ≤30 %,
  35 si ≤45 %, 10 sinon.

Plafonds : aucun A/B → 65 ; seulement 2 comparables → 55 ; référence non
confirmée → 40 ; tous les vendeurs identiques → 35.

## 3. Prix de revente

Scénarios par défaut :

```text
sale_prudent = low
sale_central = central
sale_favorable = high
```

Le prix de mise en vente recommandé :

```text
listing_price = min(high, central × (1 + negotiation_buffer))
```

`negotiation_buffer` initial = 8 %. Une stratégie “prix fort” peut utiliser
12 % pendant 14 jours. Après 14 jours sans offre qualifiée, recommander une
baisse vers la cote centrale. Après 30 jours sans offre, déclencher une revue de
liquidité et de surpaiement, jamais une baisse automatique.

## 4. Coût de revient

```text
buyer_variable_fee = hammer_or_agreed_price × buyer_fee_rate
acquisition_cost =
  purchase_price + buyer_variable_fee + buyer_fixed_fee
  + inbound_shipping + insurance + customs + acquisition_tax
  + fx_cost

preparation_cost =
  authentication + service + repair + battery + polishing
  + accessories + outbound_packaging

total_cost_before_sale = acquisition_cost + preparation_cost
seller_variable_fee = sale_price × seller_fee_rate
net_sale_proceeds =
  sale_price - seller_variable_fee - seller_fixed_fee
  - outbound_shipping - sale_tax

net_profit = net_sale_proceeds - total_cost_before_sale
roi = net_profit / total_cost_before_sale
```

Les coûts incertains possèdent `low/central/high`. Le scénario prudent utilise
les coûts hauts et le prix de vente bas.

## 5. Prix maximal d’achat

Deux contraintes s’appliquent ; retenir la plus basse.

### Contrainte de profit

```text
max_by_profit =
  net_sale_proceeds
  - non_purchase_costs
  - minimum_net_profit
```

### Contrainte de ROI

Si les frais acheteur sont `purchase_price×b + fixed` :

```text
max_by_roi =
  (net_sale_proceeds - fixed_non_purchase_costs)
  / ((1 + buyer_fee_rate) × (1 + minimum_roi))
```

```text
max_purchase_price = floor_to_increment(min(max_by_profit, max_by_roi))
```

Incrément : 10 € sous 2 000 €, 25 € de 2 000 à 5 000 €, 50 € au-dessus.
Le prix maximal n’inclut jamais une hypothèse de négociation non obtenue.

## 6. Score KAIROS

### Rentabilité — 30 points

- profit (18 pts) : 0 à 0 €, 25 à 100 €, 50 à 200 €, 75 à 350 €, 100 à 500 €
  ou plus, interpolation linéaire ;
- ROI (12 pts) : 0 à 0 %, 25 à 5 %, 50 à 10 %, 75 à 15 %, 100 à 20 % ou plus.

Les seuils en euros devront devenir configurables par segment après validation.

### Liquidité — 27,5 points

- délai (13,75) : ≤14 j=100, 30=80, 60=60, 90=40, 180=15, >180=0 ;
- profondeur (6,875) : ≥20 comps actifs/180j=100, 10=80, 5=60, 3=40, <3=15 ;
- cohérence (6,875) : reprend le score de dispersion.

### Capital et portefeuille — 20 points

- impact cash (8) : achat/capital disponible ≤20 %=100, ≤35=80, ≤50=60,
  ≤70=35, >70=0 ;
- diversification (6) : 100 si la marque représente <25 % du stock après
  achat, 70 si <40 %, 40 si <60 %, 10 sinon ;
- immobilisation (6) : ratio du capital déjà immobilisé : <30 %=100, <50=75,
  <70=45, ≥70=10.

### État — 15 points

- mécanique (6) : vérifié/révisé=100, fonctionnel=75, inconnu=40, défaut=10 ;
- cosmétique (5,25) : excellent=100, très bon=85, bon=65, correct=40,
  mauvais=10 ;
- complétude (3) : full set=100, boîte ou papiers=70, montre seule=40 ;
- originalité (0,75) : original=100, incertain=40, modification importante=0.

### Confiance — 7,5 points

Qualité annonce 35 %, comparables 30 %, vendeur 20 %, garanties 15 %. Chaque
sous-score est documenté dans la réponse.

```text
raw_score = sum(pillar_score × pillar_weight)
```

Règles de dépendance :

- confiance <40 → score plafonné à 59 et verdict au mieux Surveiller ;
- confiance 40–59 → score plafonné à 74 ;
- allocation >70 % → score plafonné à 54 ;
- délai >180 j et allocation >50 % → verdict Abandonner ;
- diversification ne peut dépasser 50/100 si liquidité <40 ;
- profit négatif en scénario central → score rentabilité=0 et Abandonner.

## 7. Délai de vente

V1 déterministe :

1. si ≥5 comparables avec dates début/fin connues : médiane des durées ;
2. sinon barème de profondeur : ≥20=21 j, 10–19=35 j, 5–9=60 j, 3–4=90 j,
   <3=180 j ;
3. multiplier par 0,85 si prix prévu ≤ cote basse ; 1,0 à la cote centrale ;
   1,35 entre centrale et haute ; 1,75 au-dessus de la haute ;
4. plafonner entre 7 et 365 jours et dégrader la confiance si dates inférées.

## 8. Verdict

Appliquer successivement : portes → plafonds → score → comparaison du prix
courant au prix maximal. Retourner `decision_reasons[]` trié par impact, y
compris les conditions qui empêchent Acheter.

## 9. Exemple de fixture

Cartier achetée 950 €, revendue 1 120 €, frais de vente 27 €, aucun autre coût :

```text
net_sale_proceeds = 1 120 - 27 = 1 093 €
net_profit = 1 093 - 950 = 143 €
roi = 143 / 950 = 15,0526 %
```

Cette fixture teste le résultat réalisé ; elle ne constitue pas une preuve de
la cote de marché de la référence.
