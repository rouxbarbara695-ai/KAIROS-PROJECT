# Décisions ouvertes

Claude ne doit pas résoudre seul ces sujets. Il peut préparer une interface ou
une configuration réversible.

| ID | Question | Valeur provisoire | Décision requise avant |
|---|---|---|---|
| D-01 | Stack d’authentification | hors premier prototype local | exposition Internet |
| D-02 | Hébergement et stockage objet | interfaces S3 compatibles | déploiement |
| D-03 | Source de change | adaptateur abstrait, cache quotidien | calcul réel multi-devise |
| D-04 | Accès Chrono24 | saisie/import assisté | collecte automatique |
| D-05 | Accès Catawiki | saisie/import assisté | collecte automatique |
| D-06 | Profil fiscal UE/hors UE | coûts manuels, Acheter bloqué si inconnu | analyse extra-UE |
| D-07 | Seuils de profit par segment | barème V1 documenté | bêta |
| D-08 | Calcul précis du délai | heuristique V1 | après données internes |
| D-09 | Portefeuille individuel ou partagé | un portefeuille partagé | authentification multi-utilisateur |
| D-10 | Conservation images/pages brutes | métadonnées, durée minimale | collecteurs |

## Questions ouvertes par l'audit de cohérence V1

Ces entrées proviennent de `docs/audit/coherence-audit-v1.md`. Les valeurs
provisoires sont **configurables et réversibles** : elles vivent dans le jeu de
règles versionné (`rule_sets`), jamais en dur dans le code. Elles ne constituent
pas une réponse métier.

### Bloquant avant la première migration (lot KAI-001 → KAI-103)

| ID | Question | Valeur provisoire | Décision requise avant |
|---|---|---|---|
| D-23 | Identifiant d'une opportunité saisie manuellement (`listings.canonical_url` est `not null`) | `canonical_url` devient `null`able ; ajout de `source_kind` (`url`/`manual`) et d'une `manual_reference` libre ; au moins une des deux clés obligatoire | KAI-101 |
| D-25 | Règles de canonicalisation d'URL et clé de déduplication | schéma+hôte en minuscules, retrait des paramètres de suivi listés en configuration, retrait du fragment, chemin sans `/` final ; empreinte SHA-256 unique par plateforme | KAI-103 |
| D-26 | Forme complète de `PlatformRule` et **valeurs réelles** des frais par plateforme | structure complète créée ; **aucune valeur de frais n'est seedée** ; frais inconnus ⇒ `Acheter` bloqué et avertissement | KAI-003 (structure), Epic 3 (valeurs) |
| D-29 | Filtrage obligatoire par portefeuille | `portfolio_id` `not null` sur `opportunities`, `comparables`, `alerts` ; un portefeuille par défaut est créé à l'initialisation | KAI-003 |
| D-30 | Source de vérité de la stratégie (`opportunities.strategy_id` vs `opportunities.strategy jsonb`) et épinglage dans l'analyse | `strategy_id` fait foi ; le champ `strategy jsonb` est supprimé ; `analyses` conserve `strategy_snapshot jsonb` + `rule_set_id` + `platform_rule_id` | KAI-003 |
| D-31 | Persistance d'une analyse `analysis_impossible` | `valuation_id` et tous les champs financiers d'`analyses` deviennent `null`able ; une colonne `status` distingue `complete` / `blocked` | KAI-003 |
| D-32 | Mécanisme d'immuabilité | déclencheurs PostgreSQL `BEFORE UPDATE OR DELETE` interdisant la modification de `analyses`, `market_valuations`, `valuation_comparables`, `listing_observations`, `opportunity_events`, `audit_log` | KAI-003 |
| D-33 | État de confirmation de la référence | `watches.identification_status` (`unconfirmed` / `confirmed` / `unknown_reference`) + `reference_confirmed_at` + `reference_confirmed_by` ; seuil d'identification automatique 80/100 configurable | KAI-102 |
| D-34 | Journal d'audit des corrections et exclusions | table `audit_log` (acteur, entité, identifiant, champ, ancienne valeur, nouvelle valeur, motif, horodatage, `request_id`), en écriture seule | KAI-103 |
| D-35 | Représentation JSON des montants et format du curseur de pagination | montants et taux sérialisés en **chaînes décimales** ; curseur opaque base64url encodant `(created_at, id)`, tri stable décroissant | KAI-101 |

### Bloquant avant l'Epic 2 — Marché

| ID | Question | Valeur provisoire | Décision requise avant |
|---|---|---|---|
| D-13 | Double comptage entre le facteur `confidence` (niveau A–E) et le facteur `source_quality` dans le poids d'un comparable | facteur `source_quality` neutralisé à 1,00 tant que la question n'est pas tranchée ; le niveau A–E reste le seul porteur de la qualité de source | KAI-203 |
| D-14 | Base de normalisation de `net_market_price` : coût acheteur tout compris ou net encaissé par le vendeur | coût acheteur tout compris (`price_eur + frais acheteur non inclus + livraison obligatoire`), sans retrait des frais vendeur | KAI-202 |
| D-15 | Sens et cumul de l'ajustement de set | facteur multiplicatif `set_factor(cible) / set_factor(comparable)`, avec `watch_only = 1,00`, `boîte ou papiers = 1,10`, `full set = 1,20`, plafond ±20 % | KAI-202 |
| D-18 | Définition de la médiane et des percentiles pondérés | interpolation linéaire sur la fonction de répartition pondérée, `Decimal` à 10 décimales, tri par prix ajusté croissant puis identifiant | KAI-203 |
| D-19 | Détection d'anomalie : prix de référence, pondération, seuil de repli IQR | appliquée au prix ajusté en EUR, médiane et MAD **non pondérées**, seuil 3,5 ; repli : hors `[Q1 − 1,5×IQR ; Q3 + 1,5×IQR]` | KAI-203 |
| D-27 | Définition d'un « comparable actif sur 180 jours » pour la profondeur de marché | `price_kind = 'asking'` et `occurred_at` dans les 180 derniers jours | KAI-304 |
| D-28 | Dates de début et de fin d'un comparable pour le calcul du délai | colonnes `observed_start_at` / `observed_end_at` créées et `null`ables ; branche 1 de l'algorithme inactive tant qu'elles ne sont pas alimentées | KAI-302 |

### Bloquant avant l'Epic 3 — Décision

| ID | Question | Valeur provisoire | Décision requise avant |
|---|---|---|---|
| D-11 | Codes et périmètre des portes : `gates.md` en définit 5, `scoring-engine.md` en définit 3 avec des codes qui se recouvrent | aucune ; les codes sont persistés dans un historique immuable, la décision doit précéder l'écriture du moteur | KAI-303 |
| D-12 | Quelle « confiance » pilote les plafonds de score, le seuil `Acheter ≥ 60` et l'alerte « confiance < 60 » : identification, valorisation, ou pilier de score | aucune ; les trois grandeurs sont nommées distinctement dans le code (`identification_confidence`, `valuation_confidence`, `confidence_pillar_score`) en attendant | KAI-304 |
| D-16 | Correction des formules du prix maximal, incohérentes avec la définition du coût et du ROI (`calculation-spec.md` §4 vs §5) | aucune ; les formules corrigées sont proposées dans l'audit mais changent les montants recommandés | KAI-302 |
| D-17 | Scénario de référence du prix maximal (prudent, central ou favorable) | aucune | KAI-302 |
| D-20 | Quantification des règles de dépendance D2, D3 et D4 de `scoring-engine.md` | aucune ; seules les dépendances déjà chiffrées dans `calculation-spec.md` §6 sont implémentées | KAI-304 |
| D-21 | Sous-pondérations du pilier État : `scoring-engine.md` omet l'originalité et ne somme qu'à 95 % | barème de `calculation-spec.md` §6 retenu (40 / 35 / 20 / 5) car c'est le seul qui somme à 100 % | KAI-304 |

### Bloquant avant l'Epic 5 — Portefeuille

| ID | Question | Valeur provisoire | Décision requise avant |
|---|---|---|---|
| D-22 | Modèle de capital du portefeuille : aucune table ne stocke le capital disponible, engagé, immobilisé ou en attente d'encaissement | aucune ; 20 points du score (pilier Capital) et `GET /portfolio/summary` en dépendent | KAI-304, KAI-504 |

## Hypothèses à valider par les fondateurs

- +10 % pour boîte **ou** papiers et +20 % pour full set ;
- score Acheter à 75, Surveiller à 55 ;
- baisse de 5 % comme alerte significative ;
- revue après 30 jours sans offre ;
- marge de négociation initiale 8 % ;
- absence de vente réalisée plafonnant la confiance à 65.
