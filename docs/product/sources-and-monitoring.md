# Sources et surveillance

## Priorités

| Source | Usage | Fréquence cible initiale | Mode de départ |
|---|---|---:|---|
| Chrono24 | Marché principal, annonces | 6–12 h | URL puis connecteur validé |
| Catawiki | Enchères et résultats | 6 h, puis 1 h sur les dernières 24 h | Connecteur prioritaire |
| Vestiaire Collective | Opportunités complémentaires | 12–24 h | URL puis expérimentation |
| WatchCharts | Cote et historique | Quotidien ou hebdomadaire | API si justifiée |
| Watchfinder / marchands | Comparables professionnels | 24–48 h | Collecte ciblée |
| Données internes | Résultats économiques réels | Temps réel | Natif |
| Taux de change | Conversion | Quotidien et à la décision | API |

## Contrat commun d’un collecteur

Chaque collecteur renvoie un objet normalisé comprenant au minimum :

- plateforme et identifiant externe ;
- URL canonique ;
- horodatage de l’observation ;
- prix, devise et statut ;
- vendeur et pays lorsque disponibles ;
- référence déclarée ;
- état et set ;
- données brutes minimales utiles ;
- statut de récupération et message d’erreur ;
- niveau de confiance.

## Gestion des changements

Une nouvelle observation déclenche un événement si elle modifie notamment :

- le prix au-delà du seuil configuré ;
- la disponibilité ;
- la fin imminente d’une enchère ;
- l’identification ;
- un comparable utilisé ;
- la cote ou le verdict.

Les fréquences restent configurables. La fréquence maximale prévue est horaire.
