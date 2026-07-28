# Spécification des calculs métier

**Ruleset initial :** `1.0.0`. Toutes les constantes décrites ici sont chargées
depuis un ruleset immuable. Les calculs utilisent `Decimal`, au moins 8 décimales
en interne, `ROUND_HALF_UP` aux sorties monétaires.

## 1. Conversion monétaire

`rate_to_eur` signifie : **nombre d’EUR pour une unité de devise source**.

```text
amount_eur = source_amount × rate_to_eur
```

Le snapshot conserve montant/devise source, `amount_eur`, `rate_to_eur`,
source du taux et `fx_rate_at`. Pour EUR, le taux est `1` et reste explicitement
stocké. Un taux dépassant sa fraîcheur configurée bloque le recalcul.

## 2. Normalisation d’un comparable

### Base économique

La cote compare ce que l’acheteur doit payer pour obtenir la montre :

```text
buyer_variable_fee_eur =
  clamp(
    base_price_eur × buyer_fee_rate,
    buyer_fee_min_eur,
    buyer_fee_max_eur
  )
buyer_total_price_eur =
  base_price_eur
  + buyer_variable_fee_eur
  + buyer_fixed_fee_eur
  + compulsory_shipping_not_included_eur
```

`base_price` est le prix demandé, marteau ou réalisé selon `price_kind`. Les
frais vendeur ne sont jamais retranchés d’un comparable ; ils sont utilisés
uniquement pour calculer le produit net de la vente de l’utilisateur.
Une borne `null` dans `clamp` signifie absence de borne. Une grille à paliers
est évaluée depuis le snapshot JSON de la règle et sa trace détaille le palier.

### Ajustement du set

Prime initiale : montre seule `0`, boîte **ou** papiers `0.10`, boîte **et**
papiers `0.20`. Pour ramener le comparable au set cible :

```text
adjusted_price_eur =
  buyer_total_price_eur
  / (1 + comparable_set_premium)
  × (1 + target_set_premium)
```

Les accessoires ordinaires valent 0. Un ajustement manuel pour accessoire rare
exige montant, motif, auteur et audit. Ne jamais cumuler automatiquement au-delà
de 20 %.

### Poids

La fiabilité de source n’est comptée qu’une fois :

```text
weight =
  source_reliability
  × recency
  × reference_similarity
  × condition_similarity
  × completeness_similarity
  × seller_independence
```

| Facteur | Coefficients initiaux |
|---|---|
| fiabilité A / B / C / D / E | 1.00 / 0.85 / 0.65 / 0.40 / 0.15 |
| âge ≤30 / 31–90 / 91–180 / 181–365 / >365 j | 1.00 / 0.90 / 0.75 / 0.55 / 0.35 |
| même référence / variante proche / autre | 1.00 / 0.60 / exclu |
| état ±1 / ±2 / inconnu | 1.00 / 0.70 / 0.50 |
| set identique / un niveau / inconnu | 1.00 / 0.80 / 0.60 |
| vendeur indépendant / doublon probable | 1.00 / 0.20 |

Classes de fiabilité :

- A : transaction réalisée confirmée par justificatif ou résultat public ;
- B : donnée d’un fournisseur/marchand reconnu avec méthode et date vérifiables ;
- C : annonce active directement observée ;
- D : dernier prix demandé avant disparition, sans preuve de vente ;
- E : donnée incomplète ou non vérifiée.

La classe décrit la fiabilité de la preuve, tandis que `price_kind` décrit sa
nature économique. Les deux champs sont obligatoires.

### Anomalies

Avec moins de 4 comparables, ne pas exclure automatiquement pour anomalie. À
partir de 4, utiliser les `adjusted_price_eur` :

1. médiane non pondérée `M` et `MAD = median(|x-M|)` ;
2. si `MAD>0`, signaler si `|x-M|/(1.4826×MAD)>3.5` ;
3. si `MAD=0`, calculer `IQR=Q3-Q1` et signaler hors
   `[Q1-1.5×IQR, Q3+1.5×IQR]` ;
4. si `MAD=IQR=0`, ne rien exclure.

Un signal est exclu par défaut de la valorisation, jamais supprimé. Une
réintégration exige un motif audité.

## 3. Cote de marché

Préconditions : au moins 2 comparables recevables, somme des poids > 0.

Pour un percentile pondéré `p`, trier par prix croissant et prendre le premier
prix dont le poids cumulé atteint `p × poids_total`.

```text
central = weighted_percentile(0.50)
low     = weighted_percentile(0.25)
high    = weighted_percentile(0.75)
```

Avec 2 à 4 comparables :

```text
low  = min(low, central × 0.90)
high = max(high, central × 1.10)
```

### `valuation_confidence` /100

```text
valuation_confidence =
  30% volume
  + 25% source_reliability
  + 20% recency
  + 15% similarity
  + 10% dispersion
```

- volume : 2=30, 3=50, 4=65, 5–7=80, ≥8=100 ;
- source : moyenne arithmétique A=100, B=85, C=65, D=40, E=15 ;
- récence : moyenne arithmétique des coefficients de récence ×100 ;
- similarité : moyenne arithmétique de
  `reference_similarity×condition_similarity×completeness_similarity×100` ;
- dispersion : 100 si largeur/central ≤10 %, 80 si ≤20 %, 60 si ≤30 %, 35 si
  ≤45 %, 10 sinon.

Plafonds appliqués dans cet ordre et tous conservés : aucun A/B →65 ; seulement
2 comparables →55 ; identité non confirmée →40 ; un seul vendeur →35.

Les trois moyennes ne réutilisent pas `final_weight`, afin de ne pas recompter
la fiabilité de source ou la récence à l’intérieur de leur propre sous-score.

## 4. Prix de vente

```text
sale_prudent   = low
sale_central   = central
sale_favorable = high
listing_price  = min(high, central × (1 + negotiation_buffer))
```

`negotiation_buffer=0.08`. Une stratégie prix fort peut utiliser `0.12` pendant
14 jours. À 14 jours sans offre qualifiée, recommander une revue vers la cote
centrale. À 30 jours, revue de liquidité/surpaiement. Aucune baisse automatique.

## 5. Coût, produit net, profit et ROI

Un coût est `fixed` ou `rate`, appartient à `acquisition`, `preparation` ou
`sale`, et possède `low|central|high`.

Pour un scénario donné :

```text
purchase_variable_rate =
  somme des taux appliqués au prix d’achat

fixed_costs_before_sale =
  frais fixes acheteur + transport entrant + assurance + douane
  + taxes fixes d’acquisition + change fixe + authentification
  + service + réparation + pile + polissage + accessoires + emballage

total_cost_before_sale =
  purchase_price × (1 + purchase_variable_rate)
  + fixed_costs_before_sale

sale_variable_cost =
  sale_price × somme des taux appliqués au prix de vente

net_sale_proceeds =
  sale_price - sale_variable_cost - fixed_sale_costs

net_profit = net_sale_proceeds - total_cost_before_sale
roi = net_profit / total_cost_before_sale
```

Si `total_cost_before_sale=0`, le ROI est `null` avec
`ROI_UNDEFINED_ZERO_COST`.

Scénarios :

- prudent : vente basse, coûts hauts, taux hauts ;
- central : vente centrale, coûts centraux ;
- favorable : vente haute, coûts bas.

## 6. Prix maximal d’achat

Le prix maximal utilise **uniquement le scénario prudent**. Poser :

- `N` = produit net prudent de vente ;
- `F` = coûts fixes prudents avant vente, hors prix d’achat ;
- `q` = somme prudente des taux appliqués au prix d’achat ;
- `Pmin` = profit net minimum ;
- `r` = ROI minimum.

```text
max_by_profit = (N - F - Pmin) / (1 + q)
max_by_roi    = (N / (1 + r) - F) / (1 + q)
raw_max_purchase_price = max(0, min(max_by_profit, max_by_roi))
```

Ces formes fermées ne sont utilisées que si tous les coûts dépendant du prix
d’achat sont linéaires dans la zone considérée.

Si un frais possède minimum, maximum, palier ou autre fonction, définir
`C(P)` comme le coût total prudent avant vente pour un prix d’achat `P`, puis
chercher le plus grand centime satisfaisant simultanément :

```text
N - C(P) >= Pmin
(N - C(P)) / C(P) >= r
```

`C(P)` doit être monotone croissante. Utiliser une recherche binaire Decimal
sur `[0, plafond_configuré]`, vérifier les deux contraintes sur le résultat,
puis arrondir vers le bas à l’incrément. La trace indique
`solver=closed_form|binary_search`, les itérations et la contrainte dominante.

Puis arrondir **vers le bas** : pas de 10 € sous 2 000 €, 25 € entre 2 000 € et
5 000 €, 50 € au-dessus. Conserver valeurs brutes, contrainte dominante et
incrément. Aucune négociation supposée n’entre dans le maximum.

## 7. Délai de vente

1. Si au moins 5 comparables `sold|ended` ont `listed_at` et `ended_at`, prendre
   la médiane de `ended_at-listed_at`.
2. Sinon compter les comparables `active` observés dans les 180 jours :
   ≥20=21 j, 10–19=35, 5–9=60, 3–4=90, <3=180.
3. Multiplier selon prix de vente : ≤low `0.85`, ≤central `1.00`,
   ≤high `1.35`, >high `1.75`.
4. Arrondir au jour supérieur, borner 7–365 jours.

Les dates inférées dégradent l’explication, jamais transformées en dates
observées.

## 8. Score et verdict

Les barèmes et règles de dépendance sont définis uniquement dans
`scoring-engine.md`. Appliquer : portes → valorisation → pricing → portefeuille
→ score brut → caps → verdict.

## 9. Fixtures arithmétiques

### Cartier réalisée

```text
achat 950 ; vente 1120 ; frais vendeur fixes 27
produit net = 1093
profit = 143
ROI = 143 / 950 = 0.1505263158
```

### Formule du maximum

```text
N=1000 ; F=100 ; q=0.05 ; Pmin=200 ; r=0.10
max_by_profit = 700 / 1.05 = 666.66666667
max_by_roi = (1000 / 1.10 - 100) / 1.05 = 770.56277056
maximum brut = 666.66666667 ; arrondi = 660
```

Au maximum brut, le profit vaut exactement 200.
