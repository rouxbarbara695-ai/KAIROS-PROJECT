# Sources et surveillance

## Modes autorisables

| Mode | MVP manuel | Condition |
|---|---:|---|
| saisie utilisateur | oui | validation des champs et audit |
| import CSV/fichier fourni | oui | provenance conservée |
| import URL assisté | conditionnel | contenu fourni ou accès autorisé |
| API officielle/partenaire | conditionnel | contrat et limites documentés |
| navigation automatisée | non par défaut | validation écrite spécifique |

Les fréquences ci-dessous sont des plafonds techniques envisagés, jamais une
autorisation :

| Source | Usage | Fréquence maximale envisagée |
|---|---|---:|
| Chrono24 | annonces | toutes les 6 h |
| Catawiki | enchères | 6 h, puis 1 h dans les dernières 24 h |
| Vestiaire Collective | annonces/offres | 12 h |
| fournisseur de cote licencié | estimation | selon contrat |
| données internes | opérations réelles | événementiel |
| taux de change | conversion | quotidien et à la décision |

## Contrat d’adaptateur

Chaque adaptateur fournit provenance, méthode d’accès, identifiant de collecte,
plateforme, identifiant externe, URL canonique, heure d’observation, nature de
prix, montant source, devise, conversion EUR, statut, vendeur, pays, référence,
état, set, fiabilité de source et erreurs.

Une erreur crée un résultat de collecte, jamais une observation factice. Une
disparition reste `unknown` jusqu’à preuve distincte d’une vente.

## Déclencheurs

Seules les modifications significatives définies dans
`workflow-and-states.md` créent un événement, une analyse ou une alerte. La
déduplication et l’idempotence sont garanties par la base.
