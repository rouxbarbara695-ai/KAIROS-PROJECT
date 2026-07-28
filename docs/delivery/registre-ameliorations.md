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
| POL-001 | P1 | Les valeurs de vocabulaire s'affichent brutes (`verified`, `watch_only`, `unconfirmed`). Il faut une table de libellés lisibles. **Décision produit requise** : les libellés visibles font partie du discours produit, pas de la technique. |
| POL-002 | P1 | Les montants s'affichent tels quels (`9500.00 EUR`). Formatage localisé attendu (`9 500,00 €`) côté présentation uniquement — la valeur transportée reste une chaîne décimale. |
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
| POL-020 | P1 | `PATCH /opportunities/{id}/watch-profile` et `/seller-profile` n'ont aucune interface : les corrections auditées ne sont accessibles que par l'API. |
| POL-021 | P1 | L'ajout d'un relevé de prix (`POST .../price-inputs`) n'est pas exposé, alors que le suivi de prix est au cœur du parcours. |
| POL-022 | P2 | Le formulaire ne couvre que le mode manuel ; la création depuis une URL d'annonce est supportée par l'API mais absente de l'interface. |
| POL-023 | P2 | Le contrôle de concurrence (`If-Match` / version de ressource) n'est pas propagé par le client web : deux corrections simultanées ne sont pas arbitrées côté interface. |
| POL-024 | P3 | La sélection de stratégie existe en base et à l'API sans écran dédié. |

## Socle technique

| ID | Priorité | Sujet |
|---|---|---|
| POL-040 | P1 | L'authentification est un mandataire de développement créé à la volée depuis une adresse de configuration. Aucun mécanisme d'identité réel : à traiter avant toute exposition hors poste local. |
| POL-041 | P1 | La table `fx_rates` n'est alimentée par aucun processus. Toute devise autre que l'euro produit donc systématiquement un avertissement et un prix non converti. **Décision produit requise** : source de taux, fréquence et fraîcheur acceptable. |
| POL-042 | P2 | Aucun test de bout en bout automatisé. Le parcours a été vérifié au navigateur manuellement ; il faut figer cette vérification dans la CI. |
| POL-043 | P2 | Redis est configuré et démarré sans être utilisé. Soit un usage réel arrive avec les moteurs, soit la dépendance sort du socle. |
| POL-044 | P2 | Les origines CORS ont une valeur par défaut en dur dans la configuration. Elles doivent devenir strictement environnementales avant tout déploiement. |
| POL-045 | P2 | Aucune limitation de débit sur l'API. |
| POL-046 | P3 | La migration initiale rejoue `database/schema.sql` d'un bloc. Les migrations suivantes devront être incrémentales et écrites à la main : documenter cette bascule. |
| POL-047 | P3 | Couverture à 93 %. Les zones non couvertes sont la résolution de change, la fabrique de session et les opérations arithmétiques de `Money` en cas d'erreur. |
| POL-048 | P3 | Les actions GitHub utilisées ciblent Node 20, déprécié par les exécuteurs. À relever lors d'une passe d'entretien de la CI. |

## Hors périmètre assumé

Ces manques ne sont pas de la dette : ils appartiennent aux lots suivants.

- Comparables, valorisation, pricing et score — Epic 2 et 3.
- Portefeuille financier, historique et notifications.
- Surveillance automatisée `KAI-405`, conditionnelle et soumise à validation
  écrite du mode d'accès.
