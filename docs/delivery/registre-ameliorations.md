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
| POL-003 | — | **Traité.** `error.tsx` et `not-found.tsx` posés ; une session expirée y est reconnue et renvoyée vers la connexion. |
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
| POL-050 | P2 | **Partiellement traité.** Apports, retraits et ajustements se saisissent désormais depuis l'écran portefeuille. Restent les achats et les ventes, qui appartiennent aux parcours d'opération (Epic 4) : leurs écritures de trésorerie en découlent et ne doivent pas se saisir à la main. |
| POL-051 | — | **Traité.** Fiabilité, niveau de risque et protections sont saisis à la création et corrigibles avec motif. |
| POL-052 | P2 | Les coûts opérationnels — révision, polissage, transport — n'ont pas d'interface de saisie. Ils sont exceptionnels (« on achète et on revend, on ne révise pas »), mais quand ils existent ils changent le profit et le prix maximal. |
| POL-053 | — | **Traité.** Une saisie manuelle déclare sa plateforme d'achat, et l'analyse en applique les frais. « Aucune » reste possible et signifie un achat de particulier à particulier — un constat, pas un oubli. |
| POL-061 | P2 | Le motif d'une transition de statut passe par `window.prompt`. C'est fonctionnel et honnête — le motif reste obligatoire — mais indigne du reste de l'interface, et impossible à styler. À remplacer par une boîte de dialogue propre. |
| POL-062 | — | **Traité.** Le cycle va de l'achat à l'encaissement. Chaque étape qui constate une opération écrit sa ligne, et le statut seul ne suffit plus à l'atteindre. |
| POL-063 | P2 | Les coûts réels d'une vente ne sont pas saisis. L'écart entre prix réalisé et montant encaissé est conservé, mais rien ne le ventile entre commission, TVA, frais de paiement et port. `sold` demande pourtant « prix réalisé, coûts réels et date d'encaissement ». Cet écart est la seule mesure possible de la justesse des grilles de frais : le ventiler permettrait de confronter la prévision au relevé. |
| POL-065 | P2 | Le côté **acheteur** n'a pas d'éditeur de barème dans l'interface : le modèle et l'API le portent, le formulaire non. Aucune plateforme relevée n'applique de tranches à l'achat, mais l'asymétrie est un piège si l'une s'y met. |
| POL-064 | P3 | Le prix demandé à la mise en vente n'est pas confronté au prix d'affichage recommandé par l'analyse. Les deux existent, l'écran ne les met pas côte à côte. |
| POL-058 | — | **Traité.** Les commissions se calculent désormais au montant et non au taux, les prix de chaque scénario étant connus : planchers et plafonds s'appliquent des deux côtés. ~~`seller_fee_min` et `seller_fee_max` sont saisis, stockés, transportés jusqu'à `PlatformFees`… puis **ignorés**. `costs_from_platform` ne lit que le taux et le frais fixe, et `Cost` ne porte aucune borne : une commission de vente plafonnée n'est donc jamais plafonnée dans les scénarios. Le côté acheteur, lui, est correct — le solveur applique bien les bornes. Conséquence : une grille à commission plafonnée surestime le coût de revente, et la TVA calculée sur cette commission hérite du même écart. Corriger demande de rendre les bornes visibles à l'évaluation des scénarios, où le prix de vente est connu.~~ |
| POL-059 | — | **Traité.** Les barèmes par tranches sont saisissables et appliqués marginalement, comme un barème d'imposition. ~~Les barèmes par tranches ne sont pas représentables : le modèle porte un taux unique, un plancher et un plafond. Vestiaire Collective facture 17 % entre 75 € et 15 000 € puis 2 500 € forfaitaires au-delà — approchable par un plafond à 2 500 € au prix d'un écart maximal de 50 € entre 14 706 € et 15 000 €, mais ce n'est pas la grille. Tant que POL-058 n'est pas traité, même cette approximation est inopérante.~~ |
| POL-060 | P2 | La TVA sur commission de Chrono24 est inconnue : la page relevée ne précise pas si les 6,5 % sont HT ou TTC. Comme c'est l'un des deux seuls lieux de revente utilisés, l'écart potentiel est de 20 % de la commission sur toutes les ventes. À vérifier auprès d'une facture réelle, pas d'une page d'aide. |
| POL-056 | P2 | Les grilles de frais réelles ne sont pas renseignées : celles saisies en vérification sont des valeurs d'illustration. Tant qu'elles ne le sont pas, tout profit affiché sur une annonce en ligne est faux — ou l'analyse refuse de se faire. À remplir depuis les pages tarifs officielles. |
| POL-057 | — | **Traité.** La plateforme de revente est un paramètre de stratégie, versionné comme le reste. Les frais acheteur viennent de l'annonce, les frais vendeur de la revente choisie : acheter et revendre au même endroit ne compte plus qu'une fois chaque commission. |
| POL-054 | P3 | Le prix affiché du scénario est calculé mais l'analyse n'expose pas les coûts ligne à ligne, seulement leur total. La règle 6 demande le détail. |
| POL-055 | P3 | L'analyse ne montre pas ce qui a changé depuis la version précédente. Un recalcul après correction devrait pouvoir se lire comme un écart, pas comme un nouveau tableau. |

## Socle technique

| ID | Priorité | Sujet |
|---|---|---|
| POL-040 | — | **Traité.** Mot de passe Argon2id, sessions opaques révocables en cookie `HttpOnly`, aucune inscription publique. Les comptes se créent en ligne de commande sur la machine qui héberge la base. |
| POL-041 | P3 | La table `fx_rates` n'est alimentée par aucun processus. Sujet **déprioritisé** (`Q-03`) : les plateformes permettent généralement de choisir sa devise, donc les montants arrivent le plus souvent déjà en euros. Comportement assumé en attendant : devise source conservée, avertissement, pas d'équivalent EUR inventé. |
| POL-042 | P2 | Aucun test de bout en bout automatisé. Le parcours a été vérifié au navigateur manuellement ; il faut figer cette vérification dans la CI. |
| POL-043 | — | **Traité.** Redis porte désormais le compteur d'échecs de connexion (POL-045). Un compteur en mémoire de processus repartirait à zéro à chaque redémarrage — un moyen trivial de remettre la limitation à plat — et ne tiendrait pas à deux instances. |
| POL-044 | — | **Traité.** Le démarrage échoue hors développement local si les origines CORS sont laissées à leur valeur locale. Le navigateur n'en dépend plus : il ne parle qu'à l'origine de l'interface, qui réécrit vers l'API. |
| POL-045 | — | **Traité pour la connexion.** Fenêtre glissante de cinq minutes, comptée par adresse IP et par adresse électronique, évaluée **avant** le calcul Argon2. Refus en `429 RATE_LIMITED`, compteurs remis à zéro par une connexion réussie, connexion préservée si Redis est injoignable. Les routes authentifiées ne sont pas limitées : elles exigent déjà une session valide, et le seul porteur d'une session est le propriétaire. À revoir si l'usage s'élargit. |
| POL-066 | P2 | Les sessions expirées ou révoquées ne sont jamais supprimées : la table `user_sessions` croît indéfiniment. Sans conséquence à un utilisateur, à nettoyer avant tout usage plus large. |
| POL-067 | P3 | Le middleware ne vérifie que la présence du cookie, pas sa validité — il n'a pas accès à la base. Une session révoquée laisse donc afficher la page avant que l'API ne réponde 401, ce que la frontière d'erreur rattrape. Correct, mais l'enchaînement mériterait d'être plus direct. |
| POL-046 | — | **Traité.** La bascule est faite : `0004` est la première migration incrémentale. Elle utilise `add column if not exists` parce que `0001` rejoue `schema.sql` d'un bloc — sur une base neuve la colonne existe déjà, sur une base existante non. |
| POL-047 | P3 | Couverture à 93 %. Les zones non couvertes sont la résolution de change, la fabrique de session et les opérations arithmétiques de `Money` en cas d'erreur. |
| POL-048 | P3 | Les actions GitHub utilisées ciblent Node 20, déprécié par les exécuteurs. À relever lors d'une passe d'entretien de la CI. |

## Hors périmètre assumé

Ces manques ne sont pas de la dette : ils appartiennent aux lots suivants.

- Portefeuille financier complet, historique et notifications — Epic 5.
- Surveillance automatisée `KAI-405`, conditionnelle et soumise à validation
  écrite du mode d'accès.
