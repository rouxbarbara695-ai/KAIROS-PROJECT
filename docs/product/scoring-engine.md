# Moteur de score KAIROS

Le score évalue l’opportunité, en utilisant notamment l’estimation de la montre.
Il n’est calculé qu’après passage des cinq portes.

## 1. Piliers

### Rentabilité — 30 points

- profit central, 60 % : 0€=0, 100€=25, 200€=50, 350€=75, ≥500€=100 ;
- ROI central, 40 % : 0%=0, 5%=25, 10%=50, 15%=75, ≥20%=100.

Interpolation linéaire, bornée 0–100.

### Liquidité — 27,5 points

- délai, 50 % : ≤14j=100, 30=80, 60=60, 90=40, 180=15, >180=0 ;
- profondeur, 25 % : ≥20 actifs/180j=100, 10=80, 5=60, 3=40, <3=15 ;
- cohérence, 25 % : sous-score de dispersion de la valorisation.

### Capital et portefeuille — 20 points

- impact cash, 40 % : allocation ≤20%=100, ≤35=80, ≤50=60, ≤70=35, >70=0 ;
- diversification, 30 % : marque après achat <25%=100, <40=70, <60=40,
  sinon 10 ;
- immobilisation, 30 % : <30%=100, <50=75, <70=45, ≥70=10.

### État — 15 points

- mécanique 40 % : vérifié/révisé=100, fonctionnel=75, inconnu=40, défaut=10 ;
- cosmétique 35 % : excellent=100, très bon=85, bon=65, correct=40,
  mauvais=10 ;
- complétude 20 % : full set=100, boîte ou papiers=70, montre seule=40 ;
- originalité 5 % : originale=100, incertaine=40, modification importante=0.

### Qualité des preuves — 7,5 points

Nom API : `evidence_quality_score`.

- qualité de la fiche, 35 % : champs utiles renseignés / champs applicables ;
- qualité des comparables, 30 % : `valuation_confidence` ;
- fiabilité vendeur, 20 % : vérifié=100, historique solide=80, inconnu=40,
  signaux négatifs=10 ;
- protections transactionnelles, 15 % : authentification+séquestre=100, une
  protection=70, recours limité=35, aucun=10.

La classe A–E d’un comparable n’est pas ce pilier.

```text
raw_score =
  profitability×0.30
  + liquidity×0.275
  + portfolio×0.20
  + condition×0.15
  + evidence_quality×0.075
```

## 2. Règles de dépendance quantifiées

Appliquer dans l’ordre et conserver chaque cap :

1. Si liquidité <40, sous-score diversification plafonné à 50 avant calcul.
2. `valuation_confidence <40` → score total plafonné à 59.
3. `valuation_confidence 40–59.99` → score total plafonné à 74.
4. `evidence_quality_score <40` → score total plafonné à 59.
5. `G2_IDENTIFICATION=passed_with_warning` → verdict plafonné à `watch`.
6. Allocation après achat > `strategy.maximum_allocation_rate` → score plafonné
   à 54.
7. Allocation entre 35 % et le maximum : `buy` exige
   `valuation_confidence≥70` et `evidence_quality_score≥65`, sinon `watch`.
8. Immobilisation ≥70 % et allocation >35 % → score plafonné à 54.
9. Délai >180 j et allocation >50 % → `pass`.
10. Profit central <0 → pilier rentabilité=0 et `pass`.
11. Risque vendeur et protections n’affectent que qualité des preuves ou
    `G5_SELLER_RISK` ; jamais la rentabilité.

Ces règles remplacent les anciennes D1–D7 non quantifiées.

## 3. Verdict

Après caps, appliquer le tableau du PRD. En cas de plusieurs règles, le verdict
le plus prudent gagne : `pass` > `analysis_impossible` > `watch` > `buy`. Un
risque d’authenticité ou vendeur justifie l’abandon même si d’autres données
manquent.

La réponse expose score brut, piliers, sous-scores, caps, conditions empêchant
`buy`, prix courant retenu et prix maximal prudent.

## 4. Arrondis

Conserver les sous-scores à 4 décimales, calculer le total sans arrondis
intermédiaires, puis exposer 2 décimales. Comparer les seuils sur la valeur non
arrondie.
