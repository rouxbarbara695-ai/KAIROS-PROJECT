# Sprint 1 — Socle décisionnel

## Objectif

Démontrer de bout en bout qu’une annonce saisie manuellement peut produire une
analyse versionnée, explicable et recalculable.

## Livrable

Un parcours API minimal :

> créer une opportunité → enregistrer l’annonce → identifier la référence →
> ajouter des comparables → produire une valorisation → calculer le prix
> maximal → calculer le score → ajouter une nouvelle observation → recalculer
> et générer une alerte.

## Backlog ordonné

1. Initialiser les applications `api` et `web`, l’environnement local et la CI.
2. Créer les migrations correspondant au schéma initial.
3. Implémenter plateformes, références, montres, annonces et observations.
4. Implémenter opportunités et portes d’éligibilité.
5. Implémenter comparables et première valorisation déterministe.
6. Implémenter coûts, prix maximal, marge et ROI.
7. Implémenter les cinq piliers du score et le verdict.
8. Versionner chaque analyse et son explication.
9. Détecter un changement de prix et produire une alerte.
10. Exposer et tester le parcours complet via l’API.

## Critères d’acceptation

- une analyse passée ne peut pas être écrasée ;
- chaque comparable expose son type, sa source, sa date et sa confiance ;
- les frais de plateforme appliqués sont datés ;
- le prix maximal est reproductible à entrées identiques ;
- un échec de porte empêche le calcul du score ;
- une baisse franchissant le prix maximal peut faire évoluer le verdict ;
- le recalcul conserve la cause du déclenchement ;
- les tests couvrent les calculs financiers et le changement de verdict.

## Non inclus

- scraping à grande échelle ;
- authentification commerciale ;
- paiement ;
- application mobile ;
- apprentissage automatique.
