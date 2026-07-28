# Audit de cohérence V1 — PRD / calculs / contrat API / schéma

> **Statut : résolu.** Chaque point C-01 à C-11, S-01 à S-16 et A-01 à A-09
> listé ci-dessous a un arbitrage enregistré dans
> `docs/decisions/audit-resolution-v2.md`, appliqué dans les spécifications V2
> (PRD, `calculation-spec.md`, `gates.md`, `scoring-engine.md`,
> `database/schema.sql`, `api-contract.md`). Ce document est conservé tel quel
> comme trace historique de l'analyse ; il ne décrit plus l'état courant du
> dépôt. Pour l'état courant, lire les documents V2 et leur registre de
> résolution.

**Date :** 27 juillet 2026
**Périmètre audité :** `docs/prd/kairos-v1.md`, `docs/product/calculation-spec.md`,
`docs/product/platform-rules.md`, `docs/product/gates.md`,
`docs/product/scoring-engine.md`, `docs/product/workflow-and-states.md`,
`docs/architecture/api-contract.md`, `docs/architecture/overview.md`,
`docs/delivery/backlog-v1.md`, `docs/delivery/sprint-01.md`,
`docs/quality/test-strategy.md`, `database/schema.sql`.

**Méthode :** aucune règle métier n'est inventée ici. Chaque écart est classé
puis renvoyé vers une entrée `docs/decisions/open-questions.md` lorsqu'une
décision des fondateurs est nécessaire.

**Légende de criticité**

| Niveau | Sens |
|---|---|
| **B1** | Bloque le lot KAI-001 → KAI-103 (socle + opportunité manuelle). |
| **B2** | Bloque un lot ultérieur (Epic 2 marché, Epic 3 décision, Epic 5 portefeuille). Le socle peut démarrer. |
| **B3** | Incohérence documentaire ou risque de reproductibilité, non bloquante. |

---

## 1. Contradictions entre documents

### C-01 — Les portes d'éligibilité sont définies deux fois, différemment (B2)

| Source | Portes |
|---|---|
| `docs/product/gates.md` | G1 Authenticité, G2 Identification, G3 Données, G4 Marché, G5 Risque vendeur |
| `docs/product/scoring-engine.md` | G1 Authenticity, G2 Data Quality, G3 Supported Market |

Les codes `G1..G3` désignent des concepts différents selon le document : `G2` est
« Identification » dans l'un et « Data Quality » dans l'autre ; `G3` est
« Données » dans l'un et « Supported Market » dans l'autre. Le contrat API
sérialise ces codes (`gates: [{"code": "G1", ...}]`) et le schéma les persiste
dans `analyses.gates` : un changement ultérieur de codes casserait l'historique,
qui est immuable par exigence.

`scoring-engine.md` ne comporte par ailleurs aucune porte « risque vendeur »,
alors que sa règle D7 affirme qu'un risque vendeur élevé « may trigger an
Eligibility Gate ».

→ **D-11**. Impact : KAI-303, `analyses.gates`, catalogue d'erreurs `GATE_FAILED`.

### C-02 — Le mot « confiance » désigne trois grandeurs différentes (B2)

Trois échelles /100 coexistent sous le même nom :

1. **confiance d'identification** — PRD §4 étape B : « identification de confiance ≥ 80/100 » ; schéma `watches.identification_confidence` ;
2. **confiance de valorisation** — `calculation-spec.md` §2, plafonds 65/55/40/35 ; schéma `market_valuations.confidence` ;
3. **pilier « Confiance » du score** — `calculation-spec.md` §6, 7,5 points, sous-critères 35/30/20/15.

S'y ajoute une quatrième notion homonyme : `confidence_level` (`a`..`e`), qui est
le **niveau de source d'un comparable**, pas une confiance /100.

Les règles qui consomment « la confiance » ne précisent pas laquelle :

- PRD §7 : « confiance ≥ 60 » pour Acheter (non qualifiée) ;
- PRD §8 : « confiance de valorisation ≥ 60 » (qualifiée) ;
- `calculation-spec.md` §6 : « confiance <40 → score plafonné à 59 », « 40–59 → 74 » (placé sous le pilier de score, donc ambigu) ;
- `workflow-and-states.md` : alerte si « confiance baisse sous 60 » (non qualifiée).

Deux implémentations défendables donnent deux verdicts différents sur les mêmes
données. C'est incompatible avec la propriété de test « à données identiques,
résultat identique ».

→ **D-12**. Impact : KAI-204, KAI-304, KAI-404.

### C-03 — Le poids d'un comparable compte deux fois la qualité de source (B2)

`calculation-spec.md` §1 :

```text
weight = confidence × recency × reference × condition × completeness
         × seller_independence × source_quality
```

Le tableau associé fournit exactement sept lignes. La première
(`Niveau A / B / C / D / E` → 1,00 / 0,85 / 0,65 / 0,40 / 0,15) et la septième
(`vente confirmée / marchand reconnu / annonce P2P` → 1,00 / 0,85 / 0,65)
décrivent la même information sous deux noms. Un comparable de niveau C
(annonce active, selon `opportunity-analysis-engine.md`) reçoit `0,65 × 0,65 =
0,4225`, soit une pénalité quadratique non intentionnelle.

Par ailleurs `calculation-spec.md` §2 réutilise « source : moyenne pondérée des
niveaux A=100 … » pour la confiance : la même dimension pèse donc trois fois.

→ **D-13**. Impact : KAI-203, KAI-204.

### C-04 — `net_market_price` mélange deux bases de prix incompatibles (B2)

```text
net_market_price =
  price_eur
  - seller_fee_included_if_known
  + buyer_fee_if_not_included
  + compulsory_shipping
```

Retrancher la commission vendeur produit le **net encaissé par le vendeur** ;
ajouter la commission acheteur produit le **coût total supporté par l'acheteur**.
Les deux opérations simultanées ne définissent aucune grandeur économique.

Le choix n'est pas neutre : le prix de revente de KAIROS (`calculation-spec.md`
§3, `listing_price`) se compare à ce que **paient les acheteurs**, tandis que
`net_sale_proceeds` (§4) retranche déjà les frais vendeur de l'opération
utilisateur. Retrancher les frais vendeur du comparable revient donc à les
déduire deux fois.

→ **D-14**. Impact : KAI-202, KAI-203, KAI-302.

### C-05 — Les formules du prix maximal contredisent la définition du coût et du ROI (B2)

`calculation-spec.md` §4 définit :

```text
total_cost_before_sale = purchase_price + purchase_price×b + fixed_costs
roi = net_profit / total_cost_before_sale
```

`calculation-spec.md` §5 propose :

```text
max_by_profit = net_sale_proceeds - non_purchase_costs - minimum_net_profit
max_by_roi    = (net_sale_proceeds - fixed_non_purchase_costs)
                / ((1 + buyer_fee_rate) × (1 + minimum_roi))
```

Aucune des deux ne satisfait la contrainte qu'elle prétend exprimer dès que
`buyer_fee_rate > 0` ou que des frais fixes existent.

**Contre-exemple profit** — `net_sale_proceeds = 1000`, frais hors achat `= 100`,
profit minimum `= 200`, `b = 0,05` :
`max_by_profit = 700` → coût total `= 700 + 35 + 100 = 835` → profit `= 165`,
**inférieur au minimum exigé de 200**.

**Contre-exemple ROI** — mêmes entrées, `minimum_roi = 0,10` :
`max_by_roi = 900 / 1,155 = 779,22` → coût total `= 918,18` → profit `= 81,82`
→ ROI `= 8,91 %`, **inférieur au minimum exigé de 10 %**.

Les formules cohérentes avec §4 sont :

```text
max_by_profit = (net_sale_proceeds - fixed_non_purchase_costs - minimum_net_profit)
                / (1 + buyer_fee_rate)

max_by_roi    = (net_sale_proceeds / (1 + minimum_roi) - fixed_non_purchase_costs)
                / (1 + buyer_fee_rate)
```

Vérification sur les mêmes entrées : `max_by_profit = 666,67` → profit exactement
200 ; `max_by_roi = 770,56` → ROI exactement 10 %.

Cette correction est une mise en cohérence arithmétique interne, mais elle change
les montants recommandés à l'utilisateur : elle doit être validée explicitement,
pas appliquée en silence.

→ **D-16**. Impact : KAI-302, propriété de test « aucun Acheter au-dessus du prix maximal ».

### C-06 — Le scénario servant de base au prix maximal n'est pas désigné (B2)

`calculation-spec.md` §4 : « Le scénario prudent utilise les coûts hauts et le
prix de vente bas. » §5 utilise `net_sale_proceeds` et `non_purchase_costs` sans
dire de quel scénario ils proviennent. Le contrat API ne renvoie qu'un seul
`max_purchase_price`. Prudent, central et favorable donnent trois prix maximaux
très différents pour la même annonce.

→ **D-17**. Impact : KAI-302.

### C-07 — Le pilier « État » n'a pas les mêmes sous-pondérations dans les deux documents (B2)

| Sous-critère | `calculation-spec.md` §6 | `scoring-engine.md` |
|---|---:|---:|
| Mécanique | 6 pts → 40 % | 40 % |
| Cosmétique | 5,25 pts → 35 % | 35 % |
| Complétude | 3 pts → 20 % | 20 % |
| Originalité | 0,75 pt → 5 % | **absent** |
| **Total** | **100 %** | **95 %** |

`scoring-engine.md` justifie l'absence par « Authenticity is intentionally
excluded from this pillar », mais originalité et authenticité sont deux notions
distinctes dans `calculation-spec.md`, qui note l'originalité tout en la traitant
aussi comme porte (G1/`gates.md`). La propriété de test « somme des poids de
piliers = 1 » est vérifiée au niveau des piliers (30+27,5+20+15+7,5 = 100) mais
pas au niveau des sous-critères d'État si l'on suit `scoring-engine.md`.

→ **D-21**. Impact : KAI-304.

### C-08 — Les règles de dépendance D2, D3, D4 ne sont pas quantifiables (B2)

`scoring-engine.md` énonce sept règles de dépendance. `calculation-spec.md` §6 en
chiffre six, qui ne recouvrent que partiellement les premières :

| Règle `scoring-engine.md` | Traduction chiffrée dans `calculation-spec.md` |
|---|---|
| D1 diversification ⇐ liquidité | « diversification ne peut dépasser 50/100 si liquidité <40 » ✅ |
| D2 confiance ⇐ profondeur de marché | **aucune** |
| D3 rentabilité ne compense pas l'immobilisation | partiellement : « allocation >70 % → score plafonné à 54 » |
| D4 « plus l'allocation est grande, plus KAIROS est strict sur *tous* les autres critères » | **aucune** — non implémentable en l'état |
| D5 confiance faible plafonne le score | ✅ (sous réserve de C-02) |
| D6 vendeur/garanties n'améliorent que la confiance | implicite |
| D7 risque vendeur peut déclencher une porte | contredit par C-01 |

D4 en particulier n'a ni seuil, ni fonction, ni liste de critères concernés.

→ **D-20**. Impact : KAI-304.

### C-09 — Le périmètre du Sprint 1 diffère entre les deux documents de delivery (B3)

`docs/delivery/backlog-v1.md` : « Sprint 1 : 001–003, 101–103. »
`docs/delivery/sprint-01.md` : dix items couvrant les Epics 0 à 4 jusqu'à la
génération d'alerte, avec pour critère d'acceptation « une baisse franchissant le
prix maximal peut faire évoluer le verdict ».

Le second décrit en réalité le périmètre cumulé des Sprints 1 à 4. Le présent
plan suit `backlog-v1.md`, conformément à la demande (KAI-001 → KAI-103).

→ Correction documentaire proposée : renommer `sprint-01.md` en objectif de
release « socle décisionnel » ou aligner son contenu sur 001–003 / 101–103.

### C-10 — L'exemple d'analyse du contrat API n'est pas un oracle exploitable (B3)

```json
"max_purchase_price": "1325.00",
"expected_profit": "275.00",
"expected_roi": "0.1800",
"decision_reasons": ["Prix inférieur au maximum de 125 €"]
```

- Le prix courant n'apparaît pas dans la réponse, alors que `decision_reasons`
  s'y réfère (il vaudrait 1 200 €, ce qui est incohérent avec l'exemple de
  création qui porte la même référence Longines à 1 800 €).
- La base de `expected_profit` et `expected_roi` n'est pas spécifiée : au prix
  courant ou au prix maximal ? Les deux lectures donnent 275 € ici par
  coïncidence arithmétique (1 200 + 325 = 1 325 + 200 = 1 525).
- `275 / 1 525 = 0,180328`, arrondi 4 décimales `0,1803` et non `0,1800`.
- `score.pillars` ne liste que deux des cinq piliers.

L'exemple ne doit pas être repris comme fixture. Le contrat doit exposer le prix
courant retenu et la base de calcul.

### C-11 — `strategy_id` et `strategy jsonb` sont deux sources de vérité (B1)

`opportunities` porte simultanément `strategy_id uuid references strategies(id)`
et `strategy jsonb not null default '{}'`. `domain-model.md` pose « Single Source
of Truth » comme principe d'architecture. Aucun document ne dit lequel fait foi
ni comment ils se réconcilient.

De plus `strategies` est versionnée dans le temps (`valid_from` / `valid_to`) et
`pricing-strategy-engine.md` exige qu'« un changement de règle ne doive pas
modifier rétroactivement une opération clôturée ». Or `analyses` ne conserve
aucune référence ni aucun instantané de la stratégie, du jeu de règles chiffrées
ni de la `platform_rule` appliqués. Le recalcul d'une analyse passée n'est donc
pas reproductible, ce qui contredit la propriété de test « à données identiques,
résultat identique » et l'exigence FR-010.

→ **D-30**. Impact : KAI-003 (schéma), KAI-101, KAI-303/304.

---

## 2. Écarts entre `database/schema.sql` et les exigences

### S-01 — Aucune table ne stocke l'équivalent EUR, le taux et son horodatage (B1)

`CLAUDE.md` règle 3 : « Stocker les montants dans leur devise source **et** leur
équivalent EUR avec le taux et l'horodatage utilisés. »

Aucune des tables monétaires (`listing_observations`, `comparables`,
`opportunity_costs`, `purchases`, `sale_listings`, `sales`, `analyses`) ne
possède de colonne `*_eur`, `fx_rate` ou `fx_rate_at`. La table `fx_rates` existe
mais **n'est référencée par aucune clé étrangère**. C'est une violation directe
d'une règle non négociable, et elle rend inapplicable le cas limite PRD §11
« devise sans taux récent : bloquer le recalcul financier ».

Le sens du taux (`EUR` par unité de devise, ou l'inverse) n'est par ailleurs
défini nulle part, alors que `fx_rates` stocke `base_currency` / `quote_currency`.

### S-02 — Une analyse `analysis_impossible` ne peut pas être persistée (B1)

`analyses` déclare `valuation_id`, `total_cost`, `expected_sale_price`,
`max_purchase_price`, `expected_profit`, `expected_roi` en `not null`. Or :

- l'énumération `recommendation` contient `analysis_impossible` ;
- PRD §7 : un échec de porte bloquante produit `analysis_impossible` ou `pass`,
  **avant** tout calcul de valorisation et de pricing ;
- PRD §11 : « prix "sur demande" : valeur `null`, aucune marge calculée » ;
- `gates.md` : « Une opportunité n'est notée que si elle franchit les portes. »

Le schéma interdit donc d'enregistrer précisément les cas que le PRD impose
d'enregistrer. `score numeric(5,2)` est correctement `null`able ; les colonnes
financières et `valuation_id` doivent l'être aussi.

### S-03 — L'immuabilité n'est garantie par aucun mécanisme (B1)

`CLAUDE.md` règle 4, FR-010, `sprint-01.md` (« une analyse passée ne peut pas
être écrasée ») et la propriété de test « une analyse publiée ne change jamais »
exigent l'immuabilité. Le schéma ne comporte ni déclencheur, ni révocation de
privilèges, ni colonne `published_at`, ni contrainte d'unicité sur
`analyses.previous_analysis_id` pour garantir une chaîne linéaire. Même constat
pour `listing_observations` (« append-only » selon `domain-model.md` et KAI-401),
`market_valuations` et `opportunity_events`.

### S-04 — Une opportunité saisie manuellement ne peut pas être créée (B1)

`listings.canonical_url text not null` et `opportunities.listing_id uuid not
null`. Or `CLAUDE.md` règle 8 : « La saisie manuelle doit fonctionner même si
aucun collecteur externe ne fonctionne » ; PRD §4 étape A : « URL **ou**
identifiant manuel » ; critère d'acceptation Epic 1 : « une Longines peut être
créée sans collecteur ».

Symétriquement, la déduplication FR-002 et la réponse `409 OPPORTUNITY_DUPLICATE`
reposent sur l'URL, mais **aucun index unique n'existe sur `canonical_url`** —
seulement sur `(platform_id, external_id)`, dont la colonne `external_id` est
`null`able (les `NULL` ne se heurtent pas en PostgreSQL). Aucune règle de
canonicalisation d'URL n'est spécifiée nulle part.

→ **D-23**, **D-25**. Impact direct : KAI-101, KAI-103.

### S-05 — Aucun état de confirmation de la référence (B1)

PRD §4 étape B impose trois issues : confirmée, corrigée, « référence inconnue ».
Une analyse chiffrée exige « une référence confirmée **ou** une identification de
confiance ≥ 80/100 ». `watches` ne porte que `identification_confidence
numeric(5,2)` : impossible de distinguer « confirmée par l'utilisateur » de
« devinée avec un score élevé », ni de tracer qui a confirmé et quand.
KAI-102 et l'erreur `REFERENCE_UNCONFIRMED` en dépendent.

### S-06 — Aucun journal d'audit pour les corrections et exclusions (B1)

PRD §6 : « Journal d'audit pour corrections, exclusions et transitions
financières. » KAI-103 s'intitule « Détection des doublons et **correction
auditée** ». `opportunity_events` ne couvre que les transitions de statut d'une
opportunité ; les corrections de champs (référence, état, set, vendeur), les
exclusions de comparables (FR-005, `PATCH /comparables/{id}`) et les écritures
financières n'ont aucune trace.

### S-07 — `platform_rules` ne peut pas porter le contrat `PlatformRule` (B1 pour la seed, B2 pour le pricing)

`platform-rules.md` exige : pays/région, commission acheteur (taux, fixe,
assiette, minimum, maximum), commission vendeur (mêmes champs), paiement et
change, livraison obligatoire et responsable, authentification/garantie,
fiscalité applicable ou inconnue, capacité d'observer une vente réalisée, méthode
d'accès autorisée, fréquences minimale et maximale, provenance et date de
vérification.

Le schéma offre `buyer_fee_rate`, `seller_fee_rate`, **un seul** `fixed_fee`,
`currency`, `rules jsonb`. Conséquences :

- `calculation-spec.md` §4 distingue `buyer_fixed_fee` et `seller_fixed_fee` :
  impossible à représenter avec un `fixed_fee` unique ;
- la méthode d'accès autorisée (D-04, D-05, `CLAUDE.md` règle 9) n'a pas de
  colonne, donc aucune garde technique n'empêche d'activer une collecte non
  validée ;
- « capacité d'observer une vente réellement réalisée » est un champ décisif pour
  le niveau de confiance d'un comparable et n'existe pas ;
- rien n'empêche deux règles de se chevaucher sur `(platform_id, période)`, alors
  que la sélection « `valid_from ≤ date < valid_to` » suppose l'unicité.

### S-08 — Les coûts incertains `low / central / high` ne sont pas représentables (B2)

`calculation-spec.md` §4 : « Les coûts incertains possèdent `low/central/high`. »
`opportunity_costs` ne porte qu'un `amount numeric(14,2)` unique. Sans cette
structure, le scénario prudent (« coûts hauts et prix de vente bas ») et le cas
limite PRD §11 « frais inconnus : scénario prudent + avertissement, pas de valeur
silencieuse » sont inapplicables.

De plus `cost_kind` ne permet pas de séparer les coûts d'acquisition des coûts de
vente : `tax` est unique alors que §4 distingue `acquisition_tax` et `sale_tax`,
et `shipping_in` / `shipping_out` sont les seuls à porter une direction. Le
calcul de `non_purchase_costs` et de `fixed_non_purchase_costs` (§5) exige de
classer chaque coût en acquisition / préparation / vente : ce classement n'est
pas déductible de manière fiable de l'énumération actuelle.

### S-09 — Le portefeuille ne stocke aucun capital (B2)

`portfolios` contient `id`, `name`, `base_currency`, `created_at`. Or :

- pilier « Capital et portefeuille » (20 points) : « impact cash : achat/capital
  disponible ≤20 %=100 … » ;
- PRD §8 : « capital renseigné » est une condition d'une recommandation Acheter ;
- `portfolio-engine.md` distingue capital disponible, engagé, immobilisé et en
  attente d'encaissement ;
- FR-014, `GET /portfolio/summary`, critère de sortie V1 « le dashboard
  réconcilie capital disponible, engagé, stock et encaissement ».

Aucune table ne permet de déclarer un apport, un retrait ou une position de
trésorerie. 20 des 100 points du score sont donc incalculables.

→ **D-22**. Impact : KAI-304, KAI-504.

### S-10 — Les traces de calcul d'un comparable ne sont pas persistées (B2)

`calculation-spec.md` exige que l'ajustement de set soit « appliqué au comparable
… puis **journalisé** », que `net_market_price` « expose ses composants », et
`CLAUDE.md` règle 6 que « toute recommandation expose ses données, règles,
exclusions et calculs ». `valuation_comparables` ne porte que `weight
numeric(8,5)` et `exclusion_reason` : ni `price_eur`, ni `net_market_price`, ni
`adjusted_price`, ni le détail des sept facteurs de pondération.

`weight numeric(8,5)` est par ailleurs trop court : le produit minimal des sept
facteurs vaut ≈ 0,00123, représenté avec une erreur relative de l'ordre du
pourcent — incompatible avec l'exigence de reproductibilité.

`comparables` n'a pas non plus de champ d'exclusion manuelle (`excluded_at`,
`excluded_by`, `exclusion_reason`) alors que `PATCH /comparables/{id}` promet
« corriger/exclure avec motif » et que la donnée source ne doit jamais être
effacée.

### S-11 — Aucune table de jeu de règles chiffrées (B2, structure à créer en B1)

`CLAUDE.md` règle 10 : « Chaque règle chiffrée porte un `rules_version`. » PRD §7 :
les seuils 75 / 55 / 60 / ×1,10 « sont la configuration initiale
`rules_version=1.0`, pas des constantes codées en dur ».

`analyses.rules_version text` et `market_valuations.rules_version text` sont deux
chaînes libres indépendantes, sans table de référence, sans contenu et sans
possibilité de rejouer une analyse ancienne avec ses propres barèmes. Elles
peuvent diverger silencieusement.

### S-12 — Le délai de vente ne dispose pas de ses données d'entrée (B2)

`calculation-spec.md` §7 : « si ≥5 comparables avec dates début/fin connues :
médiane des durées ». `comparables` ne porte qu'un `occurred_at` unique — ni date
de mise en ligne, ni date de fin. La branche 1 de l'algorithme est morte.

De même, « profondeur : ≥20 comps **actifs**/180 j » suppose une définition de
« comparable actif » qui n'existe pas (`price_kind = 'asking'` ? niveau C ?
`listing_status = 'active'` à l'observation ?).

→ **D-27**, **D-28**.

### S-13 — Le filtrage par portefeuille n'est pas garanti (B1)

`overview.md` : « filtrage de **toutes** les ressources par portefeuille ».
`opportunities.portfolio_id` est `null`able, `alerts` ne porte aucun
`portfolio_id`, et `comparables` non plus. Avec D-09 (« un portefeuille
partagé »), le multi-portefeuille reste possible plus tard : l'invariant doit
être posé dès la première migration, sous peine de reprise de données.

→ **D-29**.

### S-14 — Idempotence et déduplication d'alertes non contraintes (B2)

- Contrat API : « Les écritures financières acceptent `Idempotency-Key` » et
  « Une relance utilise la même clé d'idempotence ». Aucune table de clés
  d'idempotence ; `collection_jobs.idempotency_key` n'est pas unique.
- `workflow-and-states.md` : « Dédupliquer par `opportunity + alert_type +
  analysis_id` ». Aucun index unique sur `alerts`.

### S-15 — Enchères : les champs exigés ne sont pas modélisés (B2)

`platform-rules.md` Catawiki : « Conserver `current_bid`, `hammer_price`,
`reserve_met`, `auction_end_at` et `buyer_fees` **séparément**. »
`listing_observations` ne dispose que d'un `price` unique et d'un `raw_data
jsonb`. Le statut `auction` existe pourtant dans `opportunity_status`, et
l'alerte « enchère se termine dans 24 h puis 3 h » a besoin de `auction_end_at`
comme colonne interrogeable.

### S-16 — Points mineurs (B3)

| Réf. | Constat |
|---|---|
| S-16a | `listing_observations` unique `(listing_id, observed_at)` : deux observations au même instant se heurtent ; préférer un horodatage + identifiant de collecte. |
| S-16b | `opportunities.updated_at` n'a pas de déclencheur de mise à jour. |
| S-16c | `watches.serial_number` est en clair sans marquage de sensibilité, alors que le PRD impose « les numéros de série sont privés ». Aucune garde n'empêche leur exposition en API ou en logs. |
| S-16d | `price_kind` inclut `kairos_estimate` : un comparable portant cette valeur rendrait la valorisation circulaire. Aucune contrainte ne l'interdit. |
| S-16e | `platforms` n'a aucune ligne : la seed exigée par KAI-003 reste à écrire. |
| S-16f | `analyses.previous_analysis_id` n'est pas unique : deux analyses peuvent revendiquer le même parent, ce qui rompt la chaîne linéaire attendue par KAI-403. |

---

## 3. Écarts du contrat API

| Réf. | Constat | Criticité |
|---|---|---|
| A-01 | `POST /opportunities` renvoie un `import_status` qui n'a ni énumération, ni colonne, ni cycle de vie documenté. | B1 |
| A-02 | Aucun endpoint de confirmation de référence, alors que l'étape B du parcours est obligatoire et que KAI-102 la livre. | B1 |
| A-03 | `PATCH /opportunities/{id}` « corrige les données non historiques » sans liste des champs corrigeables. KAI-103 exige une correction auditée : le périmètre doit être explicite. | B1 |
| A-04 | Aucun endpoint d'historique d'événements, alors que l'écran 5 « Historique » est au périmètre V1. | B2 |
| A-05 | Aucun endpoint de stratégie / paramètres, alors que l'écran 7 et KAI-301 en dépendent. | B2 |
| A-06 | `GET /jobs/{id}` n'apparaît que dans la section « Asynchronisme », pas dans la table des ressources. | B3 |
| A-07 | Le catalogue d'erreurs ne couvre pas le conflit d'idempotence, le conflit d'écriture concurrente sur `PATCH`, ni la tentative de modification d'une ressource immuable. | B2 |
| A-08 | La pagination par curseur n'a ni format de curseur, ni ordre de tri documenté : deux implémentations donneront deux ordres. | B1 |
| A-09 | Le contrat ne précise pas la représentation des montants. Les exemples utilisent des chaînes (`"1800.00"`), ce qui est cohérent avec `Decimal`, mais la règle n'est pas énoncée et un client pourrait produire des nombres JSON (flottants). | B1 |

---

## 4. Décisions bloquantes, par lot

### Bloquant pour KAI-001 → KAI-103

Ces points doivent être tranchés avant d'écrire la première migration, car ils
déterminent des structures que l'immuabilité rendra coûteuses à reprendre.

| Réf. | Décision attendue | Question |
|---|---|---|
| S-04 | Identifiant d'une opportunité manuelle et clé de déduplication | D-23, D-25 |
| S-01 | Colonnes de conversion EUR obligatoires sur toute table monétaire | D-03 (existante) |
| S-02 | Nullabilité des champs financiers d'`analyses` | D-31 |
| S-03 | Mécanisme d'immuabilité (déclencheurs PostgreSQL) | D-32 |
| S-05 | État de confirmation de la référence | D-33 |
| S-06 | Table de journal d'audit | D-34 |
| S-07 | Forme complète de `platform_rules`, y compris `access_method` | D-26 |
| S-13 | `portfolio_id` obligatoire sur les ressources | D-29 |
| C-11 | Source de vérité de la stratégie et épinglage dans l'analyse | D-30 |
| A-08 / A-09 | Format de curseur et représentation `Decimal` en JSON | D-35 |

### Bloquant pour l'Epic 2 (marché) — non bloquant maintenant

C-03 (double comptage), C-04 (base de `net_market_price`), D-15 (sens de
l'ajustement de set), D-18 (définition de la médiane et des percentiles
pondérés), D-19 (anomalies), S-10, S-12.

### Bloquant pour l'Epic 3 (décision) — non bloquant maintenant

C-01 (portes), C-02 (confiance), C-05 (prix maximal), C-06 (scénario), C-07
(sous-pondérations), C-08 (dépendances), S-08 (coûts incertains), S-11 (jeu de
règles).

### Bloquant pour l'Epic 5 (portefeuille) — non bloquant maintenant

S-09 (capital du portefeuille).

---

## 5. Ce que l'audit ne tranche pas

Conformément à la règle 1 de `CLAUDE.md`, aucune des questions ci-dessus n'a été
résolue par déduction. Les valeurs provisoires proposées dans
`docs/decisions/open-questions.md` (entrées D-11 à D-35) sont des **valeurs de
configuration réversibles**, choisies pour permettre au socle de démarrer, et non
des réponses métier. Elles sont chargées depuis un jeu de règles versionné, pas
codées en dur, et toute modification produit une nouvelle `rules_version`.
