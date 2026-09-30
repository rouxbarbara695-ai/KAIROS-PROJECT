# Sources et surveillance

## Modes autorisables

| Mode | MVP | Condition |
|---|---:|---|
| saisie utilisateur | oui | validation des champs et audit |
| import CSV/fichier fourni | oui | provenance conservée |
| import URL assisté | conditionnel | contenu fourni ou accès autorisé |
| **recherche autonome par API officielle** | **oui, eBay** | identifiants du programme développeur, limites publiées respectées, aucune donnée personnelle conservée |
| API officielle/partenaire (autres) | conditionnel | contrat et limites documentés |
| navigation automatisée / extraction de pages | **non** | exclue par les conditions de la source ou par une protection technique : ne se contourne pas |

## Recherche autonome (décision du 30 septembre 2026)

Déclenchée par la confirmation de la référence d’une montre ou par une demande
d’actualisation ; **jamais en continu**. Elle est **on-demand**, pas de la
surveillance.

Une source n’est interrogée que si quatre conditions sont réunies : accès réel
prouvé, aucune exclusion contractuelle, données exactes pour la référence,
découverte automatique. Constat au 30 septembre 2026 dans
`decisions/faisabilite-recherche-autonome.md` : Catawiki (conditions : extraction
non autorisée) et Chrono24 (défi anti-robot) ne le sont pas ; eBay, par son API
officielle, est le seul mode implémenté.

Règles communes à toutes les sources :

- référence **exacte** ; variantes admises : ponctuation et casse seulement ;
  jamais de substitution d’une référence voisine ;
- une annonce écartée garde son **motif** ;
- prix demandé, enchère en cours, prix marteau et prix réalisé restent
  distincts ; une annonce active est de classe **C** au plus ;
- une disparition n’est jamais une vente ; un échec de collecte n’efface rien ;
- déduplication des annonces republiées ; aucun pseudonyme de vendeur conservé ;
- fraîcheur affichée ; une recherche récente est réutilisée ;
- au premier refus explicite (401, 403, 429) la source s’arrête, sans nouvelle
  tentative ; les autres sources continuent ;
- réglages configurables et versionnés (`SearchPolicy`), provisoires : voir
  `decisions/open-questions.md`.

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
