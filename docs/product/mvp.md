# MVP

## Objectif

Prouver qu’une opportunité peut être analysée, expliquée, recalculée et clôturée,
**sans que l’utilisateur ait à chercher lui-même les comparables**, tout en
restant utilisable sans aucun accès externe : le parcours manuel complet reste
le repli (règle 8).

> **Décision du 30 septembre 2026 (« Correction de périmètre »).** Le MVP ne
> demande plus de chercher les comparables à la main, ni par extension de
> navigateur, ni par collage de pages. La recherche est **autonome**, exécutée
> par KAIROS, déclenchée par l’ajout d’une montre (référence confirmée) ou par une
> demande d’actualisation. Elle **n’est pas une surveillance permanente**. Elle
> n’est activée que pour les sources dont le mode d’accès est validé : voir
> `sources-and-monitoring.md` et `decisions/faisabilite-recherche-autonome.md`.

## Parcours indispensable

1. Créer une opportunité manuelle ou rattacher une URL.
2. Confirmer, corriger ou déclarer inconnue la référence.
3. Qualifier état, set, vendeur, pays et frais.
4. **KAIROS cherche les comparables** dans les sources validées, contrôle
   l’identité de chaque annonce, déduplique et enregistre les retenues avec leur
   provenance. Le manuel (saisie, CSV) complète ou remplace cette étape.
5. Produire cote, confiances, coûts, scénarios, prix maximal, score et verdict.
6. Enregistrer achats, coûts, ventes et trésorerie.
7. Comparer prévision et réalisé.

## Inclus

- saisie manuelle complète (repli, toujours possible) ;
- recherche autonome de comparables **sur les sources validées** (aujourd’hui :
  API officielle eBay, prix demandés et enchères en cours) ;
- règles de plateformes saisies et versionnées ;
- analyses et journal d’audit immuables ;
- dashboard portefeuille ;
- import URL assisté uniquement si la méthode est autorisée.

## Conditionnel

- surveillance permanente d’une source explicitement autorisée ;
- alertes issues de cette surveillance ;
- recherches sauvegardées.

## Hors périmètre

Paiement, assurance, comptabilité fiscale complète, application native,
authentification automatique de montres, ML, découverte généralisée, SaaS
multi-tenant et généralisation à d’autres objets de collection.
