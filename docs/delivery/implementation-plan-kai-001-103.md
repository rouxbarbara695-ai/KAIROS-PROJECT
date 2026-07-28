# Plan d'implémentation — KAI-001 → KAI-103

**Statut :** proposition, en attente de validation. **Aucun code n'est écrit
avant accord.**
**Version :** alignée sur les spécifications V2 réconciliées
(`docs/decisions/audit-resolution-v2.md`, `database/schema.sql`,
`docs/architecture/api-contract.md`). Ce document remplace la version alignée
sur le V1, conservée par référence dans l'historique git.
**Périmètre :** Epic 0 (socle) et Epic 1 partiel, conformément à
`docs/delivery/backlog-v1.md` (Sprint 1 : KAI-001 à KAI-103). KAI-104 (écran de
saisie) n'est pas dans le lot ; `apps/web` est seulement échafaudé.

**Hors périmètre explicite :** aucun collecteur réel, aucun appel réseau
sortant, aucun paiement, aucun apprentissage automatique, aucun moteur de
valorisation, de pricing ou de scoring (Epics 2 et 3).

---

## 1. État des décisions

Toutes les décisions structurantes qui bloquaient ce lot dans l'audit V1
(D-23 à D-35) sont désormais tranchées et appliquées directement dans
`database/schema.sql`, `docs/architecture/api-contract.md` et
`docs/product/*.md` — voir `docs/decisions/audit-resolution-v2.md` pour le
détail arbitrage par arbitrage. Ce plan les prend comme données d'entrée, sans
les rediscuter.

Les questions encore ouvertes (`docs/decisions/open-questions.md`, Q-01 à
Q-10) portent sur des sujets externes (fournisseur d'authentification,
hébergement, fournisseur de taux de change, accès aux plateformes, profil
fiscal, calibration bêta). Aucune ne bloque KAI-001 à KAI-103 : le plan
utilise des ports abstraits et des valeurs de test (`rate_to_eur = 1` pour
l'EUR, aucune authentification hors local) partout où une réponse externe
manque.

---

## 2. Arborescence cible à l'issue du lot

```text
.
├── Makefile                             # bootstrap, up, migrate, test, lint, contracts
├── package.json / pnpm-workspace.yaml   # espace de travail pnpm (web + contracts)
├── .env.example                         # aucune valeur secrète
├── .github/workflows/ci.yml
├── apps/
│   ├── api/
│   │   ├── pyproject.toml               # ruff, mypy strict, pytest, coverage
│   │   ├── alembic.ini                  # script_location -> ../../infra/migrations
│   │   ├── app/
│   │   │   ├── main.py                  # create_app(), montage des routeurs
│   │   │   ├── api/v1/
│   │   │   │   ├── router.py
│   │   │   │   ├── errors.py            # catalogue -> gestionnaires HTTP
│   │   │   │   ├── pagination.py        # curseur Base64URL {"created_at","id"}
│   │   │   │   ├── concurrency.py       # ETag / If-Match -> RESOURCE_VERSION_CONFLICT
│   │   │   │   ├── idempotency.py       # Idempotency-Key -> idempotency_records
│   │   │   │   ├── schemas/             # modèles Pydantic d'entrée/sortie
│   │   │   │   └── routes/
│   │   │   │       ├── health.py
│   │   │   │       ├── opportunities.py
│   │   │   │       └── platforms.py
│   │   │   ├── shared/
│   │   │   │   ├── config.py            # pydantic-settings, typé, validé au démarrage
│   │   │   │   ├── logging.py           # JSON, request_id, masquage des secrets
│   │   │   │   ├── middleware.py        # request_id, journal d'accès, durée
│   │   │   │   ├── domain/
│   │   │   │   │   ├── money.py         # Money(Decimal, Currency) + arrondis ROUND_HALF_UP
│   │   │   │   │   ├── currency.py
│   │   │   │   │   ├── clock.py         # horloge injectable, UTC
│   │   │   │   │   ├── errors.py        # DomainError -> code du catalogue api-contract.md
│   │   │   │   │   └── page.py
│   │   │   │   ├── rules/
│   │   │   │   │   ├── loader.py        # lecture de `rulesets` par version, vérif checksum
│   │   │   │   │   └── ruleset.py       # modèle typé du JSON de ruleset (voir schema.sql)
│   │   │   │   └── infrastructure/
│   │   │   │       ├── db/engine.py, session.py, base.py
│   │   │   │       ├── db/models/*.py   # SQLAlchemy 2.0, miroir exact des migrations
│   │   │   │       └── db/repositories/*.py
│   │   │   ├── platforms/{domain,application,ports,adapters}/
│   │   │   ├── identity/{domain,application,ports,adapters}/
│   │   │   ├── opportunities/{domain,application,ports,adapters}/
│   │   │   ├── audit/{domain,application,ports,adapters}/
│   │   │   └── market/ pricing/ scoring/ monitoring/ portfolio/ notifications/ telemetry/
│   │   │                                # squelettes : __init__.py + README de périmètre
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── unit/                    # moteurs purs, sans base
│   │       ├── integration/             # PostgreSQL réel
│   │       └── contract/                # instantané OpenAPI
│   └── web/
│       ├── package.json, next.config.ts, tsconfig.json, eslint.config.mjs
│       └── src/app/{layout.tsx,page.tsx,health/page.tsx}, src/lib/api.ts
├── packages/contracts/
│   ├── package.json
│   ├── openapi.json                     # généré, versionné
│   └── src/api.d.ts                     # types TypeScript générés
├── infra/
│   ├── docker-compose.yml               # api, web, worker, postgres, redis
│   ├── docker/{api.Dockerfile,web.Dockerfile}
│   └── migrations/{env.py,script.py.mako,versions/}
├── tests/fixtures/
│   ├── cartier-must-vendome-590003.json
│   ├── omega.json
│   └── longines-l2-257-4-57-6.json
├── database/schema.sql                  # contrat de référence V2 ; les migrations
│                                         # doivent reproduire exactement ce fichier
└── docs/                                # V2, voir CLAUDE.md pour l'ordre de lecture
```

Les modules `opportunities` (orchestrateur, sans calcul) et `audit`
(événements append-only) figurent désormais explicitement dans
`docs/architecture/overview.md`. Le module `telemetry` (KPI produit,
liste blanche de propriétés, PRD §3) est ajouté au même endroit et son
squelette est créé dans ce lot, bien que son utilisation réelle commence avec
les moteurs (Epic 2/3).

**Sur `database/schema.sql`.** Ce fichier est le contrat de référence déjà
réconcilié et vérifié — il a été exécuté avec succès sur PostgreSQL 16 réel
(extensions `pgcrypto`/`btree_gist`, contrainte d'exclusion temporelle,
déclencheurs d'immuabilité et seeds compris) pendant la revue de ce lot. Les
migrations Alembic de KAI-003 doivent le reproduire à l'identique ; la CI
régénère un `pg_dump --schema-only` depuis une base migrée à blanc et échoue
sur tout écart.

---

## 3. KAI-001 — Monorepo, Docker Compose, CI (3 pts)

### Livrables

- Espace de travail pnpm à la racine (`apps/web`, `packages/contracts`) ; l'API
  Python reste gérée par `pyproject.toml` + `uv`.
- `infra/docker-compose.yml` : `postgres:16`, `redis:7`, `api`, `worker` (même
  image que l'API, commande différente, sans tâche enregistrée à ce stade),
  `web`. Volumes nommés, `healthcheck` sur chaque dépendance.
- `Makefile` : `bootstrap`, `up`, `down`, `migrate`, `seed`, `fmt`, `lint`,
  `typecheck`, `test`, `contracts`, `check` (= tout).
- `.github/workflows/ci.yml`.
- `README` de démarrage : `make bootstrap && make up` doit suffire.

### Chaîne d'outils

| Domaine | Outil | Réglage |
|---|---|---|
| Format + lint Python | `ruff` | `ruff format` et `ruff check`, ligne 88 |
| Typage Python | `mypy` | `strict = true`, `disallow_any_generics`, plugin Pydantic |
| Tests Python | `pytest`, `pytest-cov` | seuil global 75 %, seuil moteurs 90 % |
| ORM / migrations | SQLAlchemy 2.0 typé, Alembic | — |
| Validation | Pydantic v2, `pydantic-settings` | — |
| Journalisation | `structlog` | sortie JSON |
| Web | Next.js 15, TypeScript `strict`, ESLint, Prettier, Vitest | — |
| Contrats | `openapi-typescript` | génération vers `packages/contracts` |
| Sécurité | `gitleaks`, `pip-audit`, `pnpm audit` | — |

### Pipeline CI (jobs parallèles)

1. `api-quality` — `ruff format --check`, `ruff check`, `mypy`.
2. `api-tests` — services `postgres` + `redis`, tests unitaires et
   d'intégration, rapport de couverture avec les deux seuils.
3. `migrations` — `alembic upgrade head`, `alembic downgrade base`,
   `alembic upgrade head` ; puis comparaison du `pg_dump --schema-only` obtenu
   avec `database/schema.sql` ; puis `alembic check`.
4. `contracts` — génération de `openapi.json` et des types TS, échec si diff.
5. `web-quality` — `eslint`, `tsc --noEmit`, `next build`, `vitest`.
6. `security` — `gitleaks detect`, `pip-audit`, `pnpm audit --audit-level=high`.

### Critères de validation

- [ ] `make bootstrap && make up` démarre la pile sur un poste vierge, une seule commande après clonage.
- [ ] `GET /api/v1/health` répond 200 ; `GET /api/v1/health/ready` distingue l'API de PostgreSQL et de Redis.
- [ ] `make check` passe localement et en CI.
- [ ] Aucun secret dans le dépôt ; `.env.example` ne contient que des valeurs de développement inoffensives.

---

## 4. KAI-002 — Configuration typée, secrets, logs structurés, `request_id` (3 pts)

### Livrables

- `app/shared/config.py` : `Settings` Pydantic, chargé une seule fois,
  **validé au démarrage**. Champs : `environment`, `database_url`
  (`SecretStr`), `redis_url` (`SecretStr`), `log_level`, `default_currency`,
  `fx_max_age_hours` (Q-03), `active_ruleset_version` (`"1.0.0"`),
  `cursor_secret`, `dev_principal_email`.
- `app/shared/logging.py` : `structlog`, sortie JSON, champs `timestamp`
  (UTC ISO-8601), `level`, `event`, `request_id`, `route`, `status`,
  `duration_ms`, plus `opportunity_id` / `job_id` quand ils existent.
  Processeur de masquage : toute valeur `SecretStr`, tout champ nommé
  `authorization`, `token`, `password`, `serial_number`,
  `serial_number_encrypted` est remplacé par `"***"` (règle 11 de
  `CLAUDE.md`).
- `app/shared/middleware.py` : lit ou génère `X-Request-Id`, l'attache au
  contexte `structlog`, le renvoie en en-tête **et** dans chaque corps de
  réponse.
- `app/api/v1/errors.py` : catalogue d'`api-contract.md` en énumération
  `ErrorCode` unique — `VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`,
  `NOT_FOUND`, `OPPORTUNITY_DUPLICATE`, `IDEMPOTENCY_CONFLICT`,
  `RESOURCE_VERSION_CONFLICT`, `IMMUTABLE_RESOURCE`, `INVALID_TRANSITION`,
  `REFERENCE_UNCONFIRMED`, `GATE_FAILED`,
  `VALUATION_INSUFFICIENT_COMPARABLES`, `FX_RATE_UNAVAILABLE`,
  `COLLECTOR_NOT_AUTHORIZED`, `COLLECTOR_UNAVAILABLE`, `RULESET_MISSING`. Un
  gestionnaire global convertit toute `DomainError` et toute erreur Pydantic
  vers l'enveloppe exacte du contrat.
- `app/shared/domain/money.py` : `Money` immuable sur `Decimal`, contexte
  décimal à 28 chiffres, `ROUND_HALF_UP` en sortie uniquement, interdiction
  explicite de construire depuis un `float`.
- `app/shared/domain/clock.py` : horloge injectable, UTC exclusivement,
  gelable dans les tests.

### Critères de validation

- [ ] Un test échoue si une variable obligatoire manque au démarrage.
- [ ] Un test vérifie que `Money(1.1)` (flottant) lève une erreur et que `Money("1.1")` réussit.
- [ ] Un test capture les logs d'une requête portant un jeton et un numéro de série et vérifie l'absence des deux dans la sortie.
- [ ] Toute réponse, succès ou erreur, porte un `request_id` égal à l'en-tête `X-Request-Id`.
- [ ] Chaque code du catalogue a un test associant code, statut HTTP et forme de réponse.

---

## 5. KAI-003 — Migrations V2, contraintes, triggers d'immuabilité, seeds (8 pts)

Le schéma cible est `database/schema.sql`, déjà vérifié sur PostgreSQL 16 réel
dans le cadre de cette revue (extensions, contrainte d'exclusion, fonctions,
triggers, seeds). Les migrations Alembic doivent le reproduire par sections
cohérentes plutôt que le rejouer tel quel :

| # | Migration | Contenu |
|---|---|---|
| 0001 | `extensions_and_enums` | `pgcrypto`, `btree_gist` ; tous les types énumérés (`listing_status`, `price_kind`, `opportunity_source_mode`, `opportunity_status`, `recommendation`, `source_reliability_level`, `reference_confirmation_status`, `gate_status`, `analysis_state`, `job_status`, `cost_status`, `cost_phase`, `cost_calculation_mode`, `cost_basis`, `cost_kind`, `platform_access_method`, `ledger_entry_kind`) |
| 0002 | `accounts_fx_rulesets` | `users`, `portfolios`, `portfolio_members`, `fx_rates`, `rulesets` + seed du ruleset `1.0.0` avec `checksum_sha256` calculé par `digest()` |
| 0003 | `strategies` | `strategies`, `strategy_versions` |
| 0004 | `platforms` | `platforms` + seed des 7 plateformes ; `platform_rules` complet (frais acheteur/vendeur, accès, observabilité, fiscalité) + contrainte d'exclusion temporelle + trigger `platform_rules_close_only` |
| 0005 | `watch_catalog` | `watch_references`, `watches` (statut de confirmation, confiance d'identification, numéro de série chiffré), `sellers` |
| 0006 | `listings` | `listings`, `listing_observations`, `listing_observation_prices` (montants source/EUR/taux/horodatage systématiques) |
| 0007 | `opportunities` | `opportunities` (mode manuel/URL, `version` optimiste), `opportunity_price_inputs`, `reference_confirmations`, `opportunity_events` + trigger `opportunities_touch` |
| 0008 | `audit_events` | table append-only, contrainte `after_data` obligatoire pour `correct|exclude|reinstate` |
| 0009 | `market` | `comparables`, `comparable_overrides`, `market_valuations`, `valuation_comparables` (facteurs et poids en précision étendue) |
| 0010 | `analyses` | contraintes de cohérence score/champs financiers, chaîne `previous_analysis_id` unique |
| 0011 | `operations` | `opportunity_costs` (fixe/taux, low/central/high), `purchases`, `sale_listings`, `sales` |
| 0012 | `portfolio_and_jobs` | `portfolio_ledger_entries`, `idempotency_records`, `collection_jobs`, `alerts`, `telemetry_events` |
| 0013 | `immutability_and_guards` | fonctions `reject_all_mutations`, `reject_published_analysis_mutation`, `allow_platform_rule_close_only`, `enforce_authorized_collection_job` + tous les triggers associés |
| 0014 | `indexes_and_isolation` | index de lecture, index d'identité `(portfolio_id, id)` et clés composées inter-tables empêchant toute relation entre deux portefeuilles |

### Points de conception à noter

- **Aucune valeur de frais n'est seedée** pour `platform_rules` : les taux
  réels de Chrono24, Catawiki et Vestiaire Collective restent une donnée
  métier non fournie. Une plateforme sans `platform_rule` applicable renvoie
  `RULESET_MISSING`/blocage de pricing plus tard (Epic 3), sans empêcher la
  saisie manuelle ni la surveillance passive.
- **`access_method = 'manual'`, `access_authorized = false`** pour les 7
  plateformes seedées. Le trigger `enforce_authorized_collection_job` refuse
  déjà tout `collection_job` tant qu'aucune migration explicite ne change ces
  colonnes — la garde de conformité (`CLAUDE.md` règle 9) est technique, pas
  seulement documentaire.
- **Le ruleset `1.0.0`** est seedé directement en SQL avec son `config jsonb`
  complet (portes, verdict, comparables, `valuation_confidence`, pricing,
  délai de vente, score, alertes) et son empreinte SHA-256 vérifiée par
  contrainte `CHECK`. Toute lecture applicative passe par `rules/loader.py`,
  jamais par des constantes codées en dur.
- **Numéros de série** : `watches.serial_number_encrypted bytea`, jamais en
  clair, absent de tout DTO général et masqué en journalisation (KAI-002).

### Critères de validation

- [ ] `alembic upgrade head` sur une base vierge, puis `downgrade base`, puis `upgrade head` : aucune erreur.
- [ ] Le `pg_dump --schema-only` d'une base migrée est identique à `database/schema.sql` ; la CI échoue sur tout écart.
- [ ] `alembic check` ne détecte aucun écart entre les modèles SQLAlchemy et les migrations.
- [ ] Un test d'intégration prouve qu'un `UPDATE`/`DELETE` sur `audit_events`, `market_valuations`, `valuation_comparables`, `listing_observations`, `listing_observation_prices`, `opportunity_price_inputs`, `reference_confirmations`, `opportunity_events`, `rulesets`, `strategy_versions`, `portfolio_ledger_entries` échoue avec `IMMUTABLE_RESOURCE`.
- [ ] Un test prouve qu'une analyse `draft` reste modifiable et qu'une analyse `published` refuse `UPDATE`/`DELETE`.
- [ ] Un test prouve qu'insérer deux `platform_rules` à périodes chevauchantes pour la même plateforme/région échoue sur la contrainte d'exclusion.
- [ ] Un test prouve qu'un `platform_rule` existant ne peut être modifié que par la fermeture de `valid_to` ; toute autre modification échoue.
- [ ] Un test prouve qu'un `collection_job` sur une règle `access_method='manual'` échoue avec `COLLECTOR_NOT_AUTHORIZED`.
- [ ] Un test prouve qu'une relation inter-portefeuilles (ex. vendeur d'un autre portefeuille) est rejetée par une clé étrangère composée.
- [ ] La seed est idempotente (`on conflict do nothing`) : deux exécutions produisent le même état.
- [ ] Aucune ligne de `platform_rules` ne contient de taux inventé.

---

## 6. KAI-101 — Créer, lister, ouvrir une opportunité manuelle (5 pts)

### Contrat

| Méthode | Route | Notes |
|---|---|---|
| `POST` | `/api/v1/opportunities` | `source.mode ∈ {manual, url}` ; `202` avec `job_id` seulement si un import autorisé est réellement lancé |
| `GET` | `/api/v1/opportunities` | curseur Base64URL, filtres `status`, `platform_code`, `brand`, `reference`, `q` |
| `GET` | `/api/v1/opportunities/{id}` | détail, `ETag` de concurrence ; dernière analyse `null` dans ce lot |
| `GET` | `/api/v1/platforms/{code}/rules` | règle applicable à date/région, `404` si aucune |

**Création manuelle.** Le corps suit l'exemple d'`api-contract.md` :
`portfolio_id`, `source.manual_identifier`, `watch{brand, reference,
reference_status="unconfirmed", mechanical_condition, cosmetic_condition,
box, papers}`, `seller{country_code, seller_type}`, `price{amount, currency}`.
Retour synchrone `201` avec `version=1`. **Il n'existe pas d'`import_status`
pour le mode manuel** — ce champ est supprimé du contrat V2.

Le prix manuel n'est pas une colonne d'`opportunities` : il est écrit dans
`opportunity_price_inputs` (append-only), avec conversion EUR immédiate si un
taux valide existe, ou `missing_reason` sinon.

**Création par URL.** `source.mode=url`, `url`. Retour `201` si seule l'URL
est stockée pour saisie manuelle complémentaire ; `202` avec `job_id`
uniquement si l'import est effectivement autorisé (ce qui n'arrive jamais
dans ce lot, `access_authorized=false` partout).

**Règles appliquées.**

- Montants, taux et scores sérialisés en chaînes décimales JSON ; un nombre
  flottant JSON pour l'un de ces champs est refusé en `VALIDATION_ERROR`.
- Un champ inconnu est stocké `null` avec motif, jamais `0`, `false` ou `""`.
- Un prix absent (« sur demande ») est accepté ; `opportunity_price_inputs`
  porte alors `amount_source=null` et `missing_reason` obligatoire.
- La conversion EUR n'est écrite que si `fx_rates` contient un taux plus
  récent que `fx_max_age_hours` (Q-03) ; sinon `FX_RATE_UNAVAILABLE` bloque
  uniquement le calcul financier, jamais la création de l'opportunité.
- Toute ressource porte un `portfolio_id not null`, vérifié par clé
  composée sur chaque relation.

**Authentification.** Q-01 place l'authentification hors du prototype local.
Un `PrincipalProvider` est introduit derrière un port ; l'implémentation de
développement résout un principal unique depuis la configuration. Les codes
`401`/`403` sont implémentés et testés dès ce lot.

### Critères de validation

- [ ] Une Longines L2.257.4.57.6 peut être créée **en mode manuel, sans URL et sans collecteur**, puis retrouvée par `GET`.
- [ ] Le prix manuel est visible dans `opportunity_price_inputs`, jamais directement sur `opportunities`.
- [ ] Un prix absent est accepté avec `missing_reason`, sans valeur `0` ni `false` implicite.
- [ ] Une devise sans taux récent laisse `amount_eur`/`rate_to_eur` absents et renvoie un avertissement explicite, jamais une valeur silencieuse.
- [ ] La pagination par curseur est stable : insérer une ligne entre deux pages ne duplique ni n'omet d'élément.
- [ ] Une opportunité d'un autre portefeuille renvoie `404`, pas `403`.
- [ ] Les fixtures Cartier, Omega et Longines de `test-strategy.md` sont créables ; les champs inconnus y restent `null`.
- [ ] `ETag`/`If-Match` sont exposés et vérifiés sur `GET`/toute future écriture.

---

## 7. KAI-102 — Confirmer/corriger/inconnue la référence ; état, set, vendeur (5 pts)

### Contrat

| Méthode | Route | Notes |
|---|---|---|
| `PATCH` | `/api/v1/opportunities/{id}` | uniquement statut courant non financier, stratégie sélectionnée, données de présentation ; `reason` obligatoire |
| `POST` | `/api/v1/opportunities/{id}/reference-confirmations` | `{"status": "suggested\|confirmed\|corrected\|unknown", "reference_id"?, "reason"}` |
| `PATCH` | `/api/v1/opportunities/{id}/watch-profile` | correction état/set, audité |
| `PATCH` | `/api/v1/opportunities/{id}/seller-profile` | correction vendeur/pays, audité |

Une nouvelle confirmation **n'écrase pas** la précédente : chaque appel crée
une ligne dans `reference_confirmations` (append-only) et met à jour la
projection courante `watches.reference_status` /
`identification_confidence` / `reference_confirmed_by_user_id` /
`reference_confirmed_at`.

### Normalisation

Les valeurs libres sont converties en vocabulaires fermés définis dans le
ruleset `1.0.0` (`scoring.condition_scores`), **sans perdre la donnée brute**
(`watches.raw_input`) :

| Dimension | Valeurs (ruleset `1.0.0`) |
|---|---|
| État mécanique | `verified`, `functional`, `unknown`, `defect` |
| État cosmétique | `excellent`, `very_good`, `good`, `fair`, `poor` |
| Complétude | `full_set`, `box_or_papers`, `watch_only` |
| Originalité | `original`, `uncertain`, `major_modification` |
| Type de vendeur | `private`, `professional`, `unknown` |

Ces vocabulaires sont ceux déjà versionnés dans `rulesets.config` : ce lot ne
fait qu'appliquer la normalisation, il n'invente aucun barème (le mapping vers
les points reste dans le moteur de score, Epic 3).

### Validation

Trois niveaux distincts, alignés sur le PRD §8 :

1. **Recevable** — plateforme et marque suffisent à l'existence.
2. **Analysable (indicative)** — référence, prix ou motif d'absence, devise,
   état approximatif, set, pays. Manque → `GATE_FAILED` avec détail des
   champs (préfiguration de `G3_DATA_QUALITY`, évalué réellement en Epic 3).
3. **Éligible à `buy`** — identité `confirmed|corrected`, etc. **Calculé mais
   non appliqué** dans ce lot : aucune analyse n'existe encore.

### Critères de validation

- [ ] `suggested`, `confirmed`, `corrected`, `unknown` produisent quatre lignes distinctes dans `reference_confirmations` et mettent à jour la projection.
- [ ] Une référence non `confirmed|corrected` avec `identification_confidence < 80` bloque toute route exigeant une valorisation avec `REFERENCE_UNCONFIRMED`.
- [ ] Une saisie d'état libre inconnue est conservée dans `raw_input` et normalisée à `unknown`, jamais à une valeur par défaut favorable.
- [ ] Le numéro de série n'apparaît dans aucune réponse d'API par défaut ni dans aucun log.
- [ ] `watch-profile` et `seller-profile` écrivent chacun un `audit_event` avec `before_data`/`after_data` dans la même transaction que la correction.
- [ ] Les trois niveaux de validation sont testés champ par champ.

---

## 8. KAI-103 — Déduplication et journal de correction append-only (5 pts)

### Déduplication

Trois clés distinctes, exactement celles du schéma V2 :

1. `listings_canonical_url_uq` — unique `(portfolio_id, canonical_url)`.
2. `listings_external_id_uq` — unique partiel `(portfolio_id, platform_id, external_id)` où `external_id is not null`.
3. `opportunities_manual_identifier_uq` — unique partiel `(portfolio_id, manual_identifier)` où `manual_identifier is not null`.

**Canonicalisation d'URL** — schéma et hôte en minuscules, retrait de `www.`,
retrait du fragment, retrait des paramètres de suivi listés en configuration
(`utm_*`, `gclid`, `fbclid`, `ref`, …), tri des paramètres restants,
suppression du `/` final. La liste des paramètres est une donnée de
configuration, pas une constante codée en dur.

À la création, une collision renvoie `409 OPPORTUNITY_DUPLICATE` avec
`existing_opportunity_id` et `matched_on ∈ {canonical_url, external_id,
manual_identifier}`, exactement la forme du contrat.

Les entrées manuelles sans URL ni identifiant externe ne sont **jamais**
dédupliquées automatiquement (l'index sur `manual_identifier` protège
seulement l'identifiant que l'utilisateur choisit lui-même). Un doublon
probable (même marque, même référence, écart de prix sous un seuil
configurable) est signalé mais jamais fusionné sans action utilisateur.

### Correction auditée

`PATCH /opportunities/{id}` : liste blanche stricte — statut courant non
financier, stratégie sélectionnée, champs de présentation. Référence, état,
set, vendeur, prix et toute donnée financière passent par leurs commandes
dédiées (`reference-confirmations`, `watch-profile`, `seller-profile`,
`price-inputs`, `costs`), chacune exigeant `reason`.

Chaque correction écrit une ligne dans `audit_events` : `actor_user_id`,
`resource_type`, `resource_id`, `action`, `reason`, `before_data`,
`after_data`, `request_id`, `occurred_at`. La contrainte `CHECK` impose
`after_data` non nul pour `correct|exclude|reinstate`. La table est
append-only par trigger (`audit_events_append_only`).

### Critères de validation

- [ ] Deux URL différant uniquement par des paramètres de suivi ou une casse d'hôte produisent le même `canonical_url` et donc un `409` avec `matched_on=canonical_url`.
- [ ] Un même `(platform_id, external_id)` produit un `409` avec `matched_on=external_id`, y compris avec une URL différente.
- [ ] Deux saisies manuelles avec le même `manual_identifier` dans le même portefeuille produisent un `409` avec `matched_on=manual_identifier` ; avec un identifiant différent, deux opportunités distinctes coexistent sans fusion automatique.
- [ ] Une correction de référence, d'état ou de prix sans `reason` est refusée en `VALIDATION_ERROR`.
- [ ] Toute correction produit exactement une ligne dans `audit_events` ; un `UPDATE`/`DELETE` sur `audit_events` échoue avec `IMMUTABLE_RESOURCE`.
- [ ] Une tentative de correction d'un champ hors liste blanche via `PATCH /opportunities/{id}` renvoie une erreur du catalogue, pas un `500`.

---

## 9. Plan de tests du lot

| Niveau | Contenu | Emplacement |
|---|---|---|
| Unitaire | `Money` et arrondis ; canonicalisation d'URL ; encodage/décodage du curseur ; chargement et vérification du checksum du ruleset ; normalisation des vocabulaires ; niveaux de validation ; masquage des logs | `apps/api/tests/unit/` |
| Intégration | migrations aller-retour ; tous les triggers d'immuabilité et de garde ; contrainte d'exclusion des `platform_rules` ; idempotence de la seed ; isolation inter-portefeuille ; toutes les routes du lot sur PostgreSQL réel | `apps/api/tests/integration/` |
| Contrat | instantané `openapi.json` ; un test par code d'erreur du catalogue vérifiant statut et enveloppe | `apps/api/tests/contract/` |
| Fixtures | Cartier 590003, Omega, Longines L2.257.4.57.6 en JSON, chargeables par l'API, champs inconnus à `null` | `tests/fixtures/` |
| Propriétés | à données identiques, réponse identique (hors `request_id`/horodatages) ; aucun montant `NaN`/infini ; aucune valeur par défaut silencieuse sur un champ inconnu | `apps/api/tests/unit/` |

Les propriétés de `test-strategy.md` portant sur la valorisation, le pricing
et le score ne sont pas testables dans ce lot : les moteurs n'existent pas
encore (Epics 2 et 3). Elles sont des dettes explicites, pas une couverture
manquante.

**Aucun test n'effectue d'appel réseau sortant.** Les taux de change utilisent
un adaptateur en mémoire (`rate_to_eur=1` pour EUR, Q-03 pour le reste).

---

## 10. Definition of Done, story par story

| Critère `CLAUDE.md` | 001 | 002 | 003 | 101 | 102 | 103 |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Migration, domaine, API et documentation cohérents | s.o. | s.o. | ✔ | ✔ | ✔ | ✔ |
| Tests unitaires, intégration et contrat, nominal et limites | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Migrations `up` depuis base vide et contraintes SQL vérifiées | s.o. | s.o. | ✔ | ✔ | ✔ | ✔ |
| Calculs et arrondis reproduisent les fixtures | s.o. | s.o. | s.o. | ✔ | ✔ | ✔ |
| Erreurs et conflits issus du catalogue API | s.o. | ✔ | ✔ | ✔ | ✔ | ✔ |
| Logs sans secret ni donnée inutile | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Formatage, typage, lint, tests et détection de secrets verts en CI | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |

Une story dont une case reste vide n'est pas déclarée terminée.

---

## 11. Séquencement et commandes de validation

Ordre : 001 → 002 → 003 → 101 → 102 → 103. Les stories 101 à 103 partagent la
même surface d'API ; le contrat OpenAPI n'est figé qu'à la fin de 103.

```bash
make bootstrap        # dépendances API et web
make up               # postgres, redis, api, web
make migrate          # alembic upgrade head + seed plateformes/ruleset
make fmt lint typecheck
make test             # unitaires + intégration + contrats, avec couverture
make contracts        # regénère openapi.json et les types TS, échoue si diff
make check            # tout ce qui précède, identique à la CI
```

---

## 12. Limites connues à l'issue du lot

- Aucun moteur de valorisation, de pricing ni de scoring : `latest_analysis`
  vaut toujours `null` et aucun verdict n'est produit (Epics 2 et 3).
- Aucun collecteur ; `access_authorized=false` pour les 7 plateformes seedées.
  `enforce_authorized_collection_job` refuse toute tentative.
- Aucune valeur de frais n'est seedée dans `platform_rules` ; le pricing sera
  bloqué (`RULESET_MISSING` ou équivalent) tant qu'une décision métier ne
  fournit pas de frais réels pour au moins une plateforme.
- Aucune authentification réelle (Q-01) : la pile ne doit pas être exposée.
- `portfolio_ledger_entries` existe en base mais n'est pas encore alimenté ni
  consommé par une route : `GET /portfolio/summary` n'est pas livré dans ce
  lot (Epic 5).
- Le worker Redis démarre mais n'exécute aucune tâche : aucune surveillance.
- Les champs d'enchère (`reserve_met`, `auction_end_at`) existent en base mais
  aucune route ne les expose encore (Epic 4).
- Les questions Q-01 à Q-10 restent ouvertes ; aucune ne bloque ce lot.
