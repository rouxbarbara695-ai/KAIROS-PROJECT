# Pricing Strategy Engine

Le Pricing Strategy Engine transforme une cote de marché en stratégie
d’achat-revente.

## Entrées

- estimation basse, centrale et haute ;
- prix demandé ou enchère actuelle ;
- commission d’achat et de vente ;
- livraison, assurance, change et fiscalité applicable ;
- travaux et contrôle prévus ;
- marge nette ou ROI minimal ;
- durée de détention et risque ;
- stratégie de négociation.

## Sorties

- coût de revient projeté ;
- prix maximal d’achat ;
- prix de revente recommandé ;
- marge nette et ROI attendus ;
- marge de négociation ;
- scénario prudent, central et favorable.

Les frais sont versionnés par plateforme et par date. Un changement de règle ne
doit pas modifier rétroactivement une opération clôturée.
