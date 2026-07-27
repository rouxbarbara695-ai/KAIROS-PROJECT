# PRD — KAIROS V1

**Statut :** prêt pour découpage technique  
**Propriétaires métier :** Ghjulia-Clara Moreno et Bastien Roux  
**Version :** 1.0 — 28 juillet 2026

## 1. Problème

Un revendeur indépendant analyse une opportunité en agrégeant manuellement des
annonces, des ventes passées, les frais de plateformes, l’état, le set, le
risque vendeur, son capital disponible et la liquidité probable. Le résultat
est lent, difficile à reproduire et exposé à l’enthousiasme de l’achat.

KAIROS transforme une annonce en décision documentée : **acheter, surveiller ou
abandonner**, avec un prix maximal, un prix de revente, une marge, un ROI, un
délai et un niveau de confiance.

## 2. Utilisateurs et droits

### P1 — Revendeur indépendant (MVP)

- crée et analyse les opportunités ;
- renseigne ou corrige les données extraites ;
- ajoute et exclut des comparables avec justification ;
- définit stratégie, capital et seuils ;
- enregistre achat, coûts, mise en vente et vente ;
- consulte les calculs et l’historique.

### P2 — Associé (V1 interne)

Mêmes droits que P1 sur un portefeuille partagé. L’attribution d’une action à un
membre est souhaitable mais non bloquante pour le premier incrément.

### P3 — Administrateur (après MVP)

Gère les règles de plateforme, référentiels et versions de moteurs. Il ne peut
pas réécrire une analyse historique.

## 3. Objectifs mesurables

| Objectif | Indicateur | Cible V1 |
|---|---|---:|
| Décider rapidement | temps médian annonce → verdict | < 5 min hors indisponibilité externe |
| Rendre la décision vérifiable | analyses avec explication complète | 100 % |
| Réduire les erreurs de calcul | écarts sur fixtures financières | 0 |
| Apprendre du réel | ventes clôturées avec prévision/réalisé | 100 % |
| Limiter le bruit | alertes débouchant sur une action | à mesurer, seuil initial 30 % |

## 4. Parcours principal

### Étape A — Créer l’opportunité

L’utilisateur colle une URL ou choisit la saisie manuelle. Le système détecte
la plateforme, canonicalise l’URL et évite les doublons. Si l’import échoue, le
formulaire manuel est préservé.

Champs minimaux : plateforme, prix, devise, marque, référence présumée, pays du
vendeur, état, contenu du set, URL ou identifiant manuel.

### Étape B — Confirmer l’identité

KAIROS propose marque, modèle et référence. L’utilisateur confirme, corrige ou
marque “référence inconnue”. Une analyse chiffrée exige une référence confirmée
ou une identification de confiance ≥ 80/100. Les numéros de série sont privés
et ne sont jamais nécessaires pour afficher une opportunité.

### Étape C — Qualifier l’objet et le vendeur

L’utilisateur renseigne état mécanique, état cosmétique, originalité des
composants, boîte, papiers, maillons/accessoires, défauts, service connu,
vendeur professionnel/particulier et garanties de plateforme.

### Étape D — Construire le marché

KAIROS présente les comparables trouvés ou saisis. Chaque ligne montre
référence, état, set, type de prix, date, source, pays, prix normalisé, poids et
motif d’exclusion éventuel. L’utilisateur peut corriger ou exclure sans effacer
la donnée source.

### Étape E — Paramétrer l’opération

Prix demandé ou enchère actuelle, livraison, assurance, commission acheteur,
commission vendeur, change, fiscalité, contrôle, réparation, consommables,
marge/ROI minimum, horizon et prix de revente prévu.

### Étape F — Décider

L’écran résultat affiche : portes d’éligibilité, cote basse/centrale/haute,
confiance, coût total, prix maximal, scénarios, score et recommandation. Chaque
nombre ouvre une explication. Un verdict n’est jamais affiché sans date de
calcul et version des règles.

### Étape G — Suivre et clôturer

L’opportunité traverse le pipeline. Une observation significative déclenche un
recalcul, jamais l’écrasement. Après vente, l’utilisateur renseigne prix réalisé,
frais réels et date d’encaissement ; KAIROS calcule l’écart au prévisionnel.

## 5. Exigences fonctionnelles

| ID | Exigence | Priorité |
|---|---|---|
| FR-001 | Créer une opportunité par URL ou saisie manuelle | Must |
| FR-002 | Détecter et fusionner les doublons de plateforme + identifiant | Must |
| FR-003 | Confirmer/corriger la référence avant valorisation | Must |
| FR-004 | Normaliser état et complétude sans perdre les données brutes | Must |
| FR-005 | Ajouter/importer/exclure des comparables avec justification | Must |
| FR-006 | Calculer cote pondérée et intervalle de confiance | Must |
| FR-007 | Calculer coût, prix maximal, marge, ROI et trois scénarios | Must |
| FR-008 | Évaluer les portes avant le score | Must |
| FR-009 | Produire score expliqué et verdict déterministe | Must |
| FR-010 | Versionner toute analyse et ses règles | Must |
| FR-011 | Gérer pipeline, achat, coûts, mise en vente et vente | Must |
| FR-012 | Historiser les observations et détecter les changements | Must |
| FR-013 | Alerter sur changement de verdict ou seuil utile | Should |
| FR-014 | Afficher capital, stock, marges projetées/réelles | Should |
| FR-015 | Import assisté Chrono24/Catawiki puis autres sources | Should |
| FR-016 | Recherches sauvegardées et découverte automatique | Could |

## 6. Exigences non fonctionnelles

- API p95 < 500 ms hors collecte et recalcul lourd.
- Import asynchrone : état visible, délai cible < 60 s.
- Tous les timestamps en UTC, rendu dans le fuseau utilisateur.
- Montants en `numeric/Decimal`, arrondis d’affichage à 2 décimales, calculs à
  4 décimales minimum.
- Authentification sécurisée avant toute version exposée sur Internet.
- Chiffrement en transit ; secrets hors dépôt ; sauvegarde quotidienne.
- Journal d’audit pour corrections, exclusions et transitions financières.
- Accessibilité : navigation clavier, labels, contrastes WCAG AA.
- Interface responsive, desktop prioritaire.

## 7. Règles de recommandation

Les portes sont évaluées avant le score. Si une porte bloquante échoue :
`analysis_impossible` ou `pass`. Sinon :

| Condition | Verdict |
|---|---|
| score ≥ 75, prix courant ≤ prix maximal, confiance ≥ 60 | Acheter |
| score 55–74, ou prix courant entre prix maximal et prix maximal × 1,10 | Surveiller |
| score < 55, ou prix courant > prix maximal × 1,10 | Abandonner |

Les plafonds de confiance et de concentration peuvent dégrader le verdict. Ces
seuils sont la configuration initiale `rules_version=1.0`, pas des constantes
codées en dur.

## 8. Données obligatoires

Pour une **analyse indicative** : référence, prix, devise, état approximatif,
set, pays, au moins 2 comparables recevables.

Pour une **recommandation Acheter** : identité confirmée, authenticité sans
signal majeur, au moins 3 comparables dont 1 de niveau A/B ou 4 de niveau C,
confiance de valorisation ≥ 60, frais calculables et capital renseigné.

Une donnée absente est `null` avec motif ; jamais `0`, `false` ou chaîne vide par
défaut.

## 9. Écrans V1

1. **Dashboard** : capital, stock, alertes, opportunités par statut.
2. **Nouvelle opportunité** : URL/import ou formulaire.
3. **Fiche opportunité** : résumé, annonce, identité, état, comparables.
4. **Analyse** : cote, coûts, score, verdict et explications.
5. **Historique** : observations, analyses et changements de verdict.
6. **Portefeuille** : achats, stock, ventes, cash et performance.
7. **Paramètres** : stratégie, seuils et frais personnalisés.

## 10. Hors périmètre V1

Paiement, assurance, comptabilité fiscale complète, application native,
marketplace KAIROS, reconnaissance automatique d’authenticité, prédiction ML,
scraping massif, multi-tenant commercial avancé.

## 11. Cas limites principaux

- URL déjà suivie : ouvrir l’existante, proposer une nouvelle observation.
- référence ambiguë : bloquer la recommandation, permettre l’analyse brouillon.
- prix “sur demande” : valeur `null`, aucune marge calculée.
- enchère : distinguer enchère courante et coût d’acquisition tout compris.
- annonce disparue : statut `unknown` jusqu’à confirmation ; jamais `sold`.
- devise sans taux récent : bloquer le recalcul financier.
- aucun prix réalisé : valorisation possible, confiance plafonnée à 65.
- composant modifié : ajustement explicite ou porte d’authenticité/originalité.
- frais inconnus : scénario prudent + avertissement, pas de valeur silencieuse.
- prix aberrant : conserver, marquer et exclure automatiquement avec motif.

## 12. Critères de sortie V1

Le MVP est accepté lorsque les trois cas de référence (Cartier, Omega, Longines)
peuvent être saisis, calculés, recalculés et clôturés ; que toutes les sommes
sont reproductibles ; qu’un changement de prix produit une analyse distincte ;
et que le dashboard réconcilie capital disponible, engagé, stock et encaissement.
