# Registre des améliorations

Journal vivant de ce qui doit être repris, affiné ou complété. Il n'ajoute
aucune règle métier : tout point qui en exigerait une est marqué
**décision produit requise** et doit passer par `open-questions.md`.

Chaque entrée porte un identifiant stable. Priorités :

- **P1** — gêne un usage réel ou masque un défaut ;
- **P2** — à traiter avant d'élargir le périmètre ;
- **P3** — confort, à faire quand le reste est stable.

État au terme de KAI-001 → KAI-103 (parcours manuel livré, moteurs absents).

## Interface et expérience

| ID | Priorité | Sujet |
|---|---|---|
| POL-001 | ~~P1~~ | ~~Valeurs de vocabulaire affichées brutes.~~ **Traité** : `apps/web/src/lib/labels.ts` porte une première proposition de libellés, à corriger librement — c'est le seul endroit à modifier. |
| POL-002 | ~~P1~~ | ~~Montants affichés tels quels.~~ **Traité** : `formatAmount` applique un formatage localisé sans arrondir ni compléter, en conservant les décimales reçues de l'API. |
| POL-025 | P2 | L'historique d'audit n'est pas paginé dans l'interface : au-delà de la première page, les corrections anciennes ne sont pas atteignables (l'API expose pourtant un curseur). |
| POL-003 | P1 | Aucune frontière d'erreur : une erreur serveur produit l'écran d'erreur brut de Next.js. Ajouter `error.tsx` et `not-found.tsx` cohérents avec la charte. |
| POL-004 | P2 | Aucun état de chargement : les pages serveur bloquent sans retour visuel. Ajouter `loading.tsx` et des squelettes sur la liste et le détail. |
| POL-005 | P2 | Les erreurs de formulaire sont un simple paragraphe. Prévoir un retour par champ et une zone `aria-live` pour les lecteurs d'écran. |
| POL-006 | P2 | Le filtre de liste ne couvre que la marque, alors que l'API accepte aussi le statut. Exposer le statut et rendre les filtres persistants. |
| POL-007 | P2 | La pagination par curseur existe côté API mais la liste n'en consomme pas ; au-delà de la première page, les données sont invisibles. |
| POL-008 | P3 | Le thème suit uniquement les préférences système. Ajouter un sélecteur explicite clair/sombre avec persistance. |
| POL-009 | P3 | Bibliothèque de composants réduite à `Card` et `Badge`. Constituer un socle réel (champs, boutons, tableaux, états vides) avant de multiplier les écrans. |
| POL-010 | P3 | Aucune passe d'accessibilité au-delà du HTML sémantique : contrastes, focus visibles et navigation clavier restent à vérifier. |

## Parcours non exposés

L'API livrée dépasse ce que l'interface permet. Ces écarts sont volontaires
mais doivent être comblés pour que le parcours soit réellement utilisable.

| ID | Priorité | Sujet |
|---|---|---|
| POL-020 | ~~P1~~ | ~~Corrections de profil sans interface.~~ **Traité (KAI-104)** : replis « Corriger l'état et le set » et « Corriger le vendeur » sur la fiche, motif obligatoire. |
| POL-021 | ~~P1~~ | ~~Relevé de prix non exposé.~~ **Traité (KAI-104)** : repli « Ajouter un relevé de prix », avec cas du prix non communiqué. |
| POL-022 | ~~P2~~ | ~~Mode URL absent du formulaire.~~ **Traité (KAI-104)** : sélecteur manuel / annonce en ligne. |
| POL-023 | P2 | Le contrôle de concurrence (`If-Match` / version de ressource) n'est pas propagé par le client web : deux corrections simultanées ne sont pas arbitrées côté interface. |
| POL-024 | P3 | La sélection de stratégie existe en base et à l'API sans écran dédié. |
| POL-028 | — | **Traité.** Le pilier portefeuille est calculé depuis le registre : trésorerie reconstruite des mouvements, stock au coût d'acquisition. Une tranche minimale de `KAI-502` a été avancée plutôt que d'alimenter le score par des valeurs saisies. |
| POL-026 | P2 | La liste des comparables n'indique pas qu'un comparable a été écarté comme anomalie lors du dernier calcul : l'information n'existe que dans la trace de la valorisation, pas sur le comparable lui-même. |
| POL-027 | P3 | L'exclusion d'un comparable demande son motif par une invite du navigateur, faute d'un composant de dialogue. |

## Décision et analyse

| ID | Priorité | Sujet |
|---|---|---|
| POL-050 | P1 | Aucune interface d'alimentation du registre : apports de capital, achats et ventes s'écrivent en SQL. Tant que ce n'est pas fait, le pilier portefeuille ne bouge pas depuis l'application, alors que c'est lui qui bloque le plus souvent le verdict. Suite de `KAI-502`. |
| POL-051 | P2 | La fiabilité du vendeur, son niveau de risque et les protections de la transaction ne sont jamais saisis : ils retombent sur « inconnu », ce qui coûte des points au pilier des preuves et déclenche une réserve sur la porte vendeur. Le formulaire doit les demander. |
| POL-052 | P2 | Les coûts opérationnels — révision, polissage, transport — n'ont pas d'interface de saisie. Ils sont exceptionnels (« on achète et on revend, on ne révise pas »), mais quand ils existent ils changent le profit et le prix maximal. |
| POL-053 | P2 | Aucune plateforme n'est rattachée à une opportunité manuelle, donc aucun frais d'achat ni de vente n'entre dans les scénarios. Le profit affiché est celui d'une vente de particulier à particulier ; sur Catawiki ou Chrono24 il serait sensiblement plus bas. |
| POL-054 | P3 | Le prix affiché du scénario est calculé mais l'analyse n'expose pas les coûts ligne à ligne, seulement leur total. La règle 6 demande le détail. |
| POL-055 | P3 | L'analyse ne montre pas ce qui a changé depuis la version précédente. Un recalcul après correction devrait pouvoir se lire comme un écart, pas comme un nouveau tableau. |

## Socle technique

| ID | Priorité | Sujet |
|---|---|---|
| POL-040 | P1 | L'authentification est un mandataire de développement créé à la volée depuis une adresse de configuration. Aucun mécanisme d'identité réel : à traiter avant toute exposition hors poste local. |
| POL-041 | P3 | La table `fx_rates` n'est alimentée par aucun processus. Sujet **déprioritisé** (`Q-03`) : les plateformes permettent généralement de choisir sa devise, donc les montants arrivent le plus souvent déjà en euros. Comportement assumé en attendant : devise source conservée, avertissement, pas d'équivalent EUR inventé. |
| POL-042 | P2 | Aucun test de bout en bout automatisé. Le parcours a été vérifié au navigateur manuellement ; il faut figer cette vérification dans la CI. |
| POL-043 | P2 | Redis est configuré et démarré sans être utilisé. Soit un usage réel arrive avec les moteurs, soit la dépendance sort du socle. |
| POL-044 | P2 | Les origines CORS ont une valeur par défaut en dur dans la configuration. Elles doivent devenir strictement environnementales avant tout déploiement. |
| POL-045 | P2 | Aucune limitation de débit sur l'API. |
| POL-046 | P3 | La migration initiale rejoue `database/schema.sql` d'un bloc. Les migrations suivantes devront être incrémentales et écrites à la main : documenter cette bascule. |
| POL-047 | P3 | Couverture à 93 %. Les zones non couvertes sont la résolution de change, la fabrique de session et les opérations arithmétiques de `Money` en cas d'erreur. |
| POL-048 | P3 | Les actions GitHub utilisées ciblent Node 20, déprécié par les exécuteurs. À relever lors d'une passe d'entretien de la CI. |

## Hors périmètre assumé

Ces manques ne sont pas de la dette : ils appartiennent aux lots suivants.

- Portefeuille financier complet, historique et notifications — Epic 5.
- Surveillance automatisée `KAI-405`, conditionnelle et soumise à validation
  écrite du mode d'accès.
