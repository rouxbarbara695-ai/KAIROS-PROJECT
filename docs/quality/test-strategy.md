# Stratégie de tests

## Niveaux

- unitaires : moteurs purs, barèmes, arrondis, canonicalisation ;
- intégration : PostgreSQL, migrations, contraintes, triggers, repositories ;
- API : validation, contrats, auth, concurrence, idempotence ;
- propriétés : invariants financiers et déterminisme ;
- end-to-end : parcours manuel puis décision complète ;
- contrats externes : uniquement réponses figées de modes autorisés.

## Sprint 1

| Zone | Cas obligatoires |
|---|---|
| Création | manuel sans listing, URL sans import, EUR, devise non EUR avec FX |
| Déduplication | manual_identifier, URL canonique, external_id, NULL distinct |
| Identité | suggested, confirmed, corrected, unknown, auteur/date |
| Audit | correction, exclusion future, append-only, avant/après |
| Immuabilité | update/delete refusés sur audit, événement, ruleset |
| Isolation | chaque lecture/écriture filtrée par portefeuille |
| API | Decimal chaîne, curseur stable, ETag, idempotence |

## Moteurs futurs

| Zone | Cas |
|---|---|
| Marché | FX, coût acheteur, set dans les deux directions, poids sans double source, outlier, percentile pondéré |
| Confiances | identification, valorisation, preuve et A–E jamais confondues |
| Pricing | trois scénarios, frais fixes/variables/min/max, formule fermée et solveur, arrondi bas |
| Score | 5 piliers, originalité 5 %, chaque cap et seuil non arrondi |
| Gates | chaque code stable, plusieurs échecs, pas de score |
| Pipeline | transitions, compensation, vente/encaissement |
| Portefeuille | grand livre, stock, engagé, encaissement |

## Fixtures

### Cartier Must Vendôme 590003

```text
achat 950,00 EUR
vente 1 120,00 EUR
frais vendeur fixes 27,00 EUR
produit net 1 093,00 EUR
profit 143,00 EUR
ROI 0,1505263158
```

### Omega

```text
achat 750,00 EUR
vente 1 200,00 EUR
frais vendeur fixes 27,00 EUR
profit 423,00 EUR
ROI 0,5640000000
```

### Longines L2.257.4.57.6

Achat 950 €, prix demandé 1 800 €, aucune offre après trois semaines. Aucune
marge réalisée n’est calculée tant que la vente n’existe pas.

### Maximum d’achat

Avec `N=1000`, `F=100`, `q=0.05`, profit minimum 200 et ROI minimum 10 % :
maximum brut `666.66666667`, maximum arrondi `660`.

## Propriétés

- `low ≤ central ≤ high`.
- Augmenter un coût ne peut augmenter profit, ROI ou maximum.
- Même snapshot + même ruleset = mêmes octets de sortie métier.
- Analyse publiée et tables append-only refusent update/delete.
- Aucun `buy` au-dessus du maximum prudent.
- Aucun NaN/infini ; ROI `null` si coût nul.
- Poids piliers et sous-poids = 1.
- Ajouter un comparable identique et indépendant ne peut réduire le volume.
- Conversion EUR aller-retour respecte la tolérance Decimal.

## CI

Formatage, lint, types, tests unitaires, intégration PostgreSQL réel,
migrations depuis zéro, tests d’immutabilité, génération OpenAPI, détection de
secrets et audit de dépendances. Couverture moteurs ≥90 %, globale ≥75 %.
