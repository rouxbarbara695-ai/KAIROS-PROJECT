# Moteur marché

Le moteur marché estime le **coût total observé côté acheteur** pour des
comparables, puis produit une cote basse, centrale et haute. Il ne retranche
jamais les frais vendeur d’un comparable : ceux-ci concernent le produit net du
vendeur, pas le prix payé sur le marché.

## Pipeline

1. Conserver prix source, devise, type et provenance.
2. Convertir en EUR avec un taux daté.
3. Ajouter les frais acheteur et la livraison obligatoire non incluse.
4. Ajuster le set du comparable vers celui de la cible.
5. Appliquer une seule fois la fiabilité de source, puis récence, proximité,
   état, complétude et indépendance vendeur.
6. Signaler les anomalies sans supprimer la donnée.
7. Calculer médiane et percentiles pondérés selon `calculation-spec.md`.

## Sortie

La `MarketValuation` conserve cote, `valuation_confidence`, ruleset, date, liste
des comparables, composants de prix, ajustements, facteurs, poids, exclusions et
explication. Elle est immuable.
