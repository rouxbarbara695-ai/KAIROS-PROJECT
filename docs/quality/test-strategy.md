# Stratégie de tests

## Pyramide

- unitaires : moteurs purs, barèmes, arrondis, transitions ;
- intégration : PostgreSQL, migrations, repositories, API ;
- contrats : collecteurs à partir de réponses figées ;
- end-to-end : parcours manuel complet ;
- non-régression : fixtures d’opérations réelles anonymisées.

## Matrice minimale

| Zone | Cas obligatoires |
|---|---|
| Valorisation | médiane pondérée, devise, set +10/+20, outlier, 2 comps, doublon vendeur |
| Pricing | frais fixes/variables, ROI, profit minimum, arrondi d’enchère, coûts inconnus |
| Score | chaque seuil, interpolation, plafonds, dépendances, profit négatif |
| Gates | échec isolé, plusieurs échecs, expertise nécessaire |
| Pipeline | chaque transition autorisée et interdite, idempotence |
| Monitoring | observation identique, baisse, disparition, récupération après erreur |
| API | validation, auth, pagination, conflit, réponse explicable |
| Portfolio | réconciliation cash/stock/encaissement, vente clôturée |

## Fixtures métier

1. **Cartier Must Vendôme 590003** : achat 950 €, vente 1 120 €, frais 27 €,
   profit réalisé 143 €, ROI 15,0526 %.
2. **Omega** : achat 750 €, vente 1 200 €, frais 27 €, profit 423 €, ROI 56,4 %
   hors autres coûts.
3. **Longines L2.257.4.57.6** : achat 950 €, mise en vente 1 800 €, pas d’offre
   après trois semaines ; opération non vendue, marge non réalisée.

Les fixtures ne doivent pas inventer des coûts absents. Les champs inconnus
sont `null`.

## Propriétés

- `low ≤ central ≤ high`.
- augmenter un coût ne peut augmenter ni profit, ni ROI, ni prix maximal.
- à données identiques, résultat identique.
- une analyse publiée ne change jamais.
- aucun verdict Acheter si prix courant > prix maximal.
- aucun montant NaN/infini ; aucune division par zéro.
- somme des poids de piliers = 1.

## CI

À chaque PR : formatage, lint, types, tests unitaires, intégration PostgreSQL,
vérification migrations up/down, génération OpenAPI sans diff inattendu,
détection de secrets et audit de dépendances. Couverture minimale moteurs 90 %,
globale 75 % ; la couverture ne remplace pas les cas métier.
