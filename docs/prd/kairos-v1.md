# PRD — KAIROS V1

**Version documentaire :** 2.0 — 28 juillet 2026  
**Ruleset initial :** `1.0.0`  
**Propriétaires métier :** Ghjulia-Clara Moreno et Bastien Roux  
**Statut :** réconcilié après audits produit et technique

## 1. Problème et promesse

Un revendeur analyse manuellement annonces, ventes, état, set, frais, vendeur,
capital et liquidité. La décision est lente, difficile à reproduire et sensible
à l’enthousiasme de l’achat.

KAIROS évalue une opportunité d’achat-revente en estimant notamment la valeur de
marché de la montre, puis en calculant coûts, rentabilité, délai, risque et
impact sur le portefeuille. Il produit un verdict expliqué : **acheter,
surveiller ou abandonner**.

## 2. Utilisateurs V1

### Revendeur / associé

- crée et corrige les opportunités ;
- confirme ou refuse une identification ;
- ajoute, corrige et exclut des comparables avec motif ;
- renseigne stratégie, capital et coûts ;
- publie une analyse, enregistre achat et vente ;
- consulte historique et journal d’audit.

Les deux associés partagent un portefeuille. Chaque ressource appartient à ce
portefeuille. Les organisations multiples, facturation et rôles commerciaux
avancés sont hors V1.

### Administrateur futur

Versionne rulesets, stratégies et règles de plateforme. Il ne peut modifier une
analyse ou une preuve historique publiée.

## 3. Mesure

### Indicateurs produit instrumentés

| KPI | Événement / calcul | Cible initiale |
|---|---|---:|
| Temps création → verdict | `opportunity_created` à `analysis_published` | médiane < 5 min hors saisie de comparables |
| Explication complète | analyse avec toutes les traces obligatoires | 100 % |
| Prévision/réalisé | vente clôturée avec analyse de référence | 100 % |
| Utilité des alertes | alerte suivie d’une action sous 7 jours | à mesurer |

### Critères techniques de non-régression

- écart financier sur fixtures : 0 ;
- même snapshot + même ruleset = même sortie ;
- aucune analyse publiée modifiable ;
- aucune ressource accessible hors portefeuille.

Les événements de mesure sont gérés par un module `telemetry`; aucun numéro de
série, URL privée ou montant détaillé n’y est envoyé.

## 4. Parcours principal

### A — Créer

Choisir `manual` ou `url`. Une création manuelle reçoit un
`manual_identifier` unique dans le portefeuille. Une URL est canonicalisée,
mais l’échec d’import n’empêche jamais la saisie.

Le prix manuel est conservé dans une série append-only distincte des
observations d’annonce.

Champs minimaux de création : mode, prix ou absence motivée, devise, marque,
référence présumée ou inconnue, pays vendeur, état approximatif et set.

### B — Identifier

La référence prend l’un des statuts : `unconfirmed`, `suggested`, `confirmed`,
`corrected`, `unknown`. Une confirmation conserve auteur et date.

Une analyse de décision complète exige `confirmed|corrected`. Un score
automatique d’identification ≥ 80 autorise une **valorisation indicative** avec
`G2_IDENTIFICATION=passed_with_warning`, mais le verdict est plafonné à `watch`
jusqu’à confirmation humaine.

### C — Qualifier

Renseigner mécanique, cosmétique, originalité, boîte, papiers, accessoires,
défauts, service, vendeur, pays, garanties et signaux d’authenticité.

### D — Construire le marché

Ajouter des comparables. Chaque preuve affiche nature de prix, date, source,
fiabilité A–E, prix source, coût total acheteur EUR, ajustement de set, poids,
statut et motif d’exclusion. Corriger ou exclure crée un événement d’audit ; la
donnée source reste intacte.

### E — Paramétrer

Choisir une stratégie versionnée. Saisir coûts d’acquisition, préparation et
vente, chacun fixe ou proportionnel avec bornes basse/centrale/haute. Épingler
la règle de plateforme applicable et le taux de change.

### F — Décider

Afficher cinq portes, cote, `valuation_confidence`, trois scénarios, coût, prix
maximal prudent, délai, cinq piliers, `evidence_quality_score`, plafonds et
verdict. Chaque nombre expose ses composants.

### G — Suivre et clôturer

Une nouvelle donnée crée une nouvelle observation et, si nécessaire, une
nouvelle analyse. Après encaissement, KAIROS compare profit, ROI et durée prévus
aux résultats. Cette comparaison alimente une revue humaine des règles.

## 5. Exigences fonctionnelles

| ID | Exigence | Priorité |
|---|---|---|
| FR-001 | Créer par saisie manuelle ou URL | Must |
| FR-002 | Dédupliquer URL canonique, identifiant externe et identifiant manuel | Must |
| FR-003 | Confirmer/corriger/refuser la référence avec audit | Must |
| FR-004 | Normaliser état et set sans perdre le brut | Must |
| FR-005 | Ajouter/corriger/exclure des comparables avec motif | Must |
| FR-006 | Calculer cote pondérée et `valuation_confidence` | Must |
| FR-007 | Calculer trois scénarios, prix maximal, profit, ROI et délai | Must |
| FR-008 | Évaluer les cinq portes avant le score | Must |
| FR-009 | Produire score et verdict déterministes et expliqués | Must |
| FR-010 | Épingler ruleset, stratégie, plateforme et FX dans toute analyse | Must |
| FR-011 | Gérer pipeline, trésorerie, achat, coûts, vente et encaissement | Must |
| FR-012 | Conserver observations, analyses et audit append-only | Must |
| FR-013 | Alerter uniquement sur un seuil utile et dédupliquer | Should |
| FR-014 | Réconcilier capital, stock, encours et performance | Should |
| FR-015 | Import assisté conforme sur une source validée | Could |
| FR-016 | Recherches sauvegardées et découverte automatique | Future |

## 6. Exigences non fonctionnelles

- API p95 < 500 ms hors jobs.
- UTC en base ; fuseau utilisateur à l’affichage.
- `Decimal/numeric`, calcul à 8 décimales minimum, arrondi monétaire
  `ROUND_HALF_UP` à 2 décimales uniquement aux frontières.
- JSON représente montants, taux et scores décimaux par des chaînes.
- Authentification avant exposition Internet ; contrôle de portefeuille sur
  chaque requête.
- Transactions atomiques pour publier une analyse.
- Journal d’audit append-only.
- Accessibilité WCAG AA et interface desktop responsive.
- Sauvegarde quotidienne et test de restauration trimestriel.

## 7. Portes et verdict

Les codes de portes sont immuables :

`G1_AUTHENTICITY`, `G2_IDENTIFICATION`, `G3_DATA_QUALITY`,
`G4_MARKET_SUPPORT`, `G5_SELLER_RISK`.

Si une porte bloque, aucun score n’est calculé. Sinon :

| Condition après plafonds | Verdict |
|---|---|
| score ≥ 75, prix courant ≤ prix maximal prudent, `valuation_confidence ≥ 60`, identité confirmée et capital disponible | `buy` |
| score 55–74, ou prix entre 100 % et 110 % du maximum, ou avertissement empêchant `buy` | `watch` |
| score < 55, prix > 110 % du maximum, profit central négatif ou règle de risque bloquante | `pass` |

Le verdict ne peut être meilleur que les plafonds du score. Les seuils sont dans
le ruleset `1.0.0`, jamais codés en dur.

## 8. Données minimales

### Analyse impossible persistable

Une opportunité peut publier `analysis_impossible` avec portes et raisons, sans
valorisation, score ni champs financiers.

### Valorisation indicative

Identité au moins suggérée, prix connu, devise convertible, état, set et au
moins deux comparables recevables.

### Verdict `buy`

- identité confirmée/corrigée ;
- les cinq portes nommées ci-dessus sont passées ;
- au moins trois comparables dont un A/B, ou quatre C ;
- `valuation_confidence ≥ 60` ;
- coûts prudent calculables ;
- capital disponible connu.

Une absence est `null` avec code de motif, jamais zéro implicite.

## 9. Écrans

1. Dashboard.
2. Nouvelle opportunité.
3. Identité, état, set et vendeur.
4. Comparables.
5. Analyse et explications.
6. Historique et audit.
7. Portefeuille.
8. Stratégies et paramètres.

## 10. Hors périmètre V1

Tout accès automatisé non validé, paiement, assurance, comptabilité fiscale
complète, application native, authentification automatique de montres,
machine learning, découverte généralisée, multi-tenant commercial et autres
catégories de collection.

## 11. Cas limites

- URL déjà suivie : `409` avec ressource existante.
- URL différente mais même `(plateforme, external_id)` : même doublon.
- référence inconnue : analyse impossible, opportunité conservée.
- prix sur demande : montant `null`, pas de pricing.
- enchère : conserver enchère, marteau, réserve, frais et fin séparément.
- annonce disparue : `unknown`, jamais `sold` sans preuve.
- FX expiré ou absent : bloquer le calcul monétaire.
- frais inconnus : borne prudente ou `analysis_impossible`.
- outlier : conserver, signaler, exclure par défaut avec motif.
- modification importante : noter l’originalité ; `G1_AUTHENTICITY` échoue
  seulement si elle crée un risque d’authenticité ou d’identification.

## 12. Critères de sortie

Les cas Cartier, Omega et Longines sont créables sans collecteur, valorisés,
analysés, recalculés et clôturés. Les montants sont reproductibles, les analyses
publiées sont immuables, les corrections sont auditées et le dashboard
réconcilie le grand livre, le stock et les encaissements.
