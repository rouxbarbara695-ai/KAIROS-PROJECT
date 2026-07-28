# Plan d'implémentation — KAI-001 → KAI-103

**Statut :** proposition, en attente de validation. **Aucun code n'est écrit
avant accord.**
**Périmètre :** Epic 0 (socle) et Epic 1 partiel, conformément à
`docs/delivery/backlog-v1.md` (« Sprint 1 : 001–003, 101–103 »). KAI-104 (écran
de saisie) n'est pas dans le lot ; `apps/web` est seulement échafaudé.

**Hors périmètre explicite :** aucun collecteur réel, aucun appel réseau sortant,
aucun paiement, aucun apprentissage automatique, aucun moteur de valorisation,
de pricing ou de scoring.

---

## 1. Décisions à valider avant la première ligne de code

Le plan ci-dessous suppose les valeurs provisoires D-23, D-25, D-26, D-29, D-30,
D-31, D-32, D-33, D-34 et D-35 de `docs/decisions/open-questions.md`. Elles sont
structurelles : les valider maintenant évite une reprise de données une fois
l'immuabilité en place. Les questions D-11 à D-22 concernent les Epics 2, 3 et 5
et ne bloquent pas ce lot.

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
│   │   │   │   ├── pagination.py        # curseur opaque (D-35)
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
│   │   │   │   │   ├── money.py         # Money(Decimal, Currency) + arrondis
│   │   │   │   │   ├── currency.py
│   │   │   │   │   ├── clock.py         # horloge injectable, UTC
│   │   │   │   │   ├── errors.py        # DomainError -> code du catalogue
│   │   │   │   │   └── page.py
│   │   │   │   ├── rules/
│   │   │   │   │   ├── loader.py        # chargement + empreinte du jeu de règles
│   │   │   │   │   ├── ruleset.py       # modèle typé
│   │   │   │   │   └── definitions/1.0.yaml
│   │   │   │   └── infrastructure/
│   │   │   │       ├── db/engine.py, session.py, base.py
│   │   │   │       ├── db/models/*.py   # SQLAlchemy 2.0, miroir des migrations
│   │   │   │       └── db/repositories/*.py
│   │   │   ├── platforms/{domain,application,ports,adapters}/
│   │   │   ├── identity/{domain,application,ports,adapters}/
│   │   │   ├── opportunities/{domain,application,ports,adapters}/
│   │   │   ├── audit/{domain,application,ports,adapters}/
│   │   │   └── market/ pricing/ scoring/ monitoring/ portfolio/ notifications/
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
├── database/schema.sql                  # régénéré depuis les migrations, vérifié en CI
└── docs/                                # inchangé, sauf corrections listées §9
```

**Note sur `opportunities/`.** `docs/architecture/overview.md` liste huit modules
métier et n'en prévoit pas pour l'opportunité, alors que `domain-model.md` en
fait l'orchestrateur. Le module `opportunities/` est ajouté comme orchestrateur ;
il ne contient aucun calcul. `audit/` est également ajouté (S-06). Ces deux
ajouts sont signalés en §9 comme corrections documentaires à valider.

**Note sur `database/schema.sql`.** Il se présente aujourd'hui comme « contrat de
conception avant la création des migrations ». Une fois les migrations écrites,
deux sources de vérité divergeraient. Proposition : après KAI-003, il est
**régénéré** par `pg_dump --schema-only` sur une base migrée à blanc, et la CI
échoue en cas d'écart.

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
2. `api-tests` — services `postgres` + `redis`, tests unitaires et d'intégration,
   rapport de couverture avec les deux seuils.
3. `migrations` — `alembic upgrade head`, `alembic downgrade base`,
   `alembic upgrade head` ; puis comparaison du `pg_dump` obtenu avec
   `database/schema.sql` ; puis `alembic check` (aucune migration manquante par
   rapport aux modèles).
4. `contracts` — génération de `openapi.json` et des types TS, échec si diff.
5. `web-quality` — `eslint`, `tsc --noEmit`, `next build`, `vitest`.
6. `security` — `gitleaks detect`, `pip-audit`, `pnpm audit --audit-level=high`.

### Critères de validation

- [ ] `make bootstrap && make up` démarre la pile sur un poste vierge, une seule commande après clonage.
- [ ] `GET /api/v1/health` répond 200 ; `GET /api/v1/health/ready` distingue l'API de PostgreSQL et de Redis (`overview.md`).
- [ ] `make check` passe localement et en CI.
- [ ] Aucun secret dans le dépôt ; `.env.example` ne contient que des valeurs de développement inoffensives.

---

## 4. KAI-002 — Configuration typée, secrets, logs structurés, `request_id` (3 pts)

### Livrables

- `app/shared/config.py` : `Settings` Pydantic, chargé une seule fois, **validé
  au démarrage** (échec rapide si une variable obligatoire manque). Champs :
  `environment`, `database_url` (`SecretStr`), `redis_url` (`SecretStr`),
  `log_level`, `default_currency`, `fx_max_age_hours` (D-03),
  `rules_version`, `cursor_secret`, `dev_principal_email`.
- `app/shared/logging.py` : `structlog`, sortie JSON, champs
  `timestamp` (UTC ISO-8601), `level`, `event`, `request_id`, `route`,
  `status`, `duration_ms`, plus `opportunity_id` / `job_id` quand ils existent.
  Processeur de masquage : toute valeur `SecretStr`, tout champ nommé
  `authorization`, `token`, `password`, `serial_number` est remplacé par
  `"***"` (S-16c, PRD §6).
- `app/shared/middleware.py` : lit ou génère `X-Request-Id`, l'attache au
  contexte `structlog`, le renvoie en en-tête **et** dans chaque corps de réponse
  (`request_id`, exigé par le contrat API).
- `app/api/v1/errors.py` : le catalogue documenté devient une énumération
  `ErrorCode` unique. Un gestionnaire global convertit toute `DomainError` et
  toute erreur de validation Pydantic vers l'enveloppe exacte du contrat
  (`error.code`, `message`, `field`, `details`, `request_id`).
- `app/shared/domain/money.py` : `Money` immuable sur `Decimal`, contexte
  décimal à 28 chiffres, `ROUND_HALF_UP` en sortie uniquement, interdiction
  explicite de construire depuis un `float`.
- `app/shared/domain/clock.py` : horloge injectable, UTC exclusivement, gelable
  dans les tests.

### Critères de validation

- [ ] Un test échoue si une variable obligatoire manque au démarrage.
- [ ] Un test vérifie que `Money(1.1)` (flottant) lève une erreur et que `Money("1.1")` réussit.
- [ ] Un test capture les logs d'une requête portant un jeton et un numéro de série et vérifie l'absence des deux dans la sortie.
- [ ] Toute réponse, succès ou erreur, porte un `request_id` égal à l'en-tête `X-Request-Id`.
- [ ] Chaque code du catalogue de `api-contract.md` a un test associant code, statut HTTP et forme de réponse.

---

## 5. KAI-003 — Migrations initiales et jeu de données plateformes (5 pts)

Douze migrations, chacune réversible. Les écarts par rapport à
`database/schema.sql` correspondent aux constats S-01 à S-16 de l'audit et aux
valeurs provisoires D-23 à D-35.

| # | Migration | Contenu | Écarts vs `schema.sql` |
|---|---|---|---|
| 0001 | `extensions_and_enums` | `pgcrypto`, `btree_gist` ; toutes les énumérations existantes | + `source_kind`, `identification_status`, `cost_phase`, `analysis_status`, `platform_access_method` |
| 0002 | `accounts_and_portfolios` | `users`, `portfolios`, `portfolio_members`, `strategies` | `strategies.is_default` ; contrainte d'unicité d'un seul défaut par portefeuille |
| 0003 | `rule_sets` | `rule_sets(id, version unique, status, payload jsonb, checksum, published_at)` | **nouveau** (S-11) |
| 0004 | `platforms` | `platforms`, `platform_rules` étendue | + `buyer_fee_fixed/min/max/basis`, `seller_fee_fixed/min/max/basis`, `country_code`, `shipping_required`, `shipping_payer`, `authentication_included`, `tax_regime`, `can_observe_realized_sale`, `access_method`, `min_interval_seconds`, `max_interval_seconds`, `source_url`, `verified_at` ; contrainte d'exclusion sur les périodes qui se chevauchent (S-07) |
| 0005 | `watch_catalog` | `watch_references`, `watches`, `sellers` | + `watches.identification_status`, `reference_confirmed_at`, `reference_confirmed_by` (S-05) |
| 0006 | `listings` | `listings`, `listing_observations` | `canonical_url` `null`able + `source_kind` + `url_fingerprint` + `manual_reference` + index unique partiels (S-04) ; observations + `price_eur`, `fx_rate`, `fx_rate_at`, `fx_rate_id` (S-01) ; clé unique `(listing_id, observed_at, collection_id)` (S-16a) |
| 0007 | `opportunities` | `opportunities`, `opportunity_events` | `portfolio_id not null` (S-13) ; suppression de `strategy jsonb` (C-11) ; déclencheur `updated_at` (S-16b) |
| 0008 | `market` | `fx_rates`, `comparables`, `market_valuations`, `valuation_comparables` | comparables + `price_eur`/`fx_*`, `excluded_at/by/reason`, `observed_start_at/end_at` (S-12), interdiction de `price_kind = 'kairos_estimate'` (S-16d) ; `valuation_comparables` + `net_market_price`, `adjusted_price`, `factors jsonb`, `weight numeric(12,8)` (S-10) |
| 0009 | `analyses` | `analyses` | `valuation_id` et champs financiers `null`ables + colonne `status` (S-02) ; + `rule_set_id`, `strategy_snapshot jsonb`, `platform_rule_id`, `current_price`/`current_price_eur`, `published_at` (C-10, C-11) ; unicité de `previous_analysis_id` (S-16f) |
| 0010 | `operations` | `opportunity_costs`, `purchases`, `sale_listings`, `sales` | coûts + `phase`, `amount_low`/`amount_central`/`amount_high`, `is_estimated` (S-08) ; colonnes EUR partout (S-01) |
| 0011 | `jobs_alerts_audit` | `collection_jobs`, `alerts`, `audit_log`, `idempotency_keys` | `collection_jobs.idempotency_key` unique ; index unique d'alerte `(opportunity_id, alert_type, analysis_id)` (S-14) ; `audit_log` **nouveau** (S-06) ; `idempotency_keys` **nouveau** (S-14) |
| 0012 | `immutability_triggers` | fonction `raise_immutable()` + déclencheurs `BEFORE UPDATE OR DELETE` sur `analyses`, `market_valuations`, `valuation_comparables`, `listing_observations`, `opportunity_events`, `audit_log` | **nouveau** (S-03) |
| 0013 | `seed_platforms` | insertion de `chrono24`, `catawiki`, `vestiaire_collective`, `watchcharts`, `watchfinder`, `independent_dealer`, `internal` ; `access_method = 'manual'` pour toutes | **aucune valeur de frais n'est insérée** (D-26) |

### Points de conception à noter

- **Aucun taux de commission n'est seedé.** Les valeurs réelles de Chrono24,
  Catawiki et Vestiaire Collective sont des données métier non documentées dans
  le dépôt ; les inventer violerait la règle 1 de `CLAUDE.md`. Une plateforme
  sans `platform_rule` applicable renvoie `RULE_VERSION_MISSING` au moment du
  pricing et bloque `Acheter`, sans empêcher la saisie ni la surveillance.
- **`access_method = 'manual'` pour toutes les plateformes**, conformément à
  D-04, D-05 et à la règle 9. Aucun collecteur ne peut être activé tant que la
  colonne n'est pas modifiée par une migration explicite.
- **Le jeu de règles `1.0`** est chargé depuis
  `app/shared/rules/definitions/1.0.yaml` et inséré dans `rule_sets` avec son
  empreinte SHA-256. Il contient les barèmes de `calculation-spec.md` et les
  seuils du PRD §7, tous configurables. Les entrées non tranchées (D-11 à D-22)
  y figurent en `null` : un moteur qui les lirait échouerait explicitement plutôt
  que de deviner.
- **Numéros de série** : conservés mais exclus par défaut de tous les schémas de
  sortie et masqués en journalisation.

### Critères de validation

- [ ] `alembic upgrade head` sur une base vierge, puis `downgrade base`, puis `upgrade head` : aucune erreur.
- [ ] Le `pg_dump --schema-only` d'une base migrée à blanc est identique à `database/schema.sql` régénéré ; la CI échoue sur tout écart.
- [ ] `alembic check` ne détecte aucun écart entre les modèles SQLAlchemy et les migrations.
- [ ] Un test d'intégration prouve qu'un `UPDATE` et un `DELETE` sur `analyses`, `market_valuations` et `listing_observations` échouent au niveau PostgreSQL.
- [ ] Un test prouve qu'insérer deux `platform_rules` à périodes chevauchantes pour la même plateforme échoue.
- [ ] Un test prouve qu'un comparable avec `price_kind = 'kairos_estimate'` est rejeté.
- [ ] La seed est idempotente : deux exécutions produisent le même état.
- [ ] Aucune ligne de `platform_rules` ne contient de taux inventé.

---

## 6. KAI-101 — Créer, lister, ouvrir une opportunité (5 pts)

### Contrat

| Méthode | Route | Notes |
|---|---|---|
| `POST` | `/api/v1/opportunities` | `source.mode ∈ {url, manual}` |
| `GET` | `/api/v1/opportunities` | curseur, filtres `status`, `platform_code`, `brand`, `reference`, `q` |
| `GET` | `/api/v1/opportunities/{id}` | détail ; `latest_analysis` vaut `null` dans ce lot |
| `GET` | `/api/v1/platforms/{code}/rules` | règle applicable à une date, `404` si aucune |

**Création.** Le corps suit l'exemple de `api-contract.md`. En mode `url`, ce lot
**enregistre** l'URL, détecte la plateforme depuis son hôte et la canonicalise ;
il ne récupère rien. La réponse `201` porte `import_status = "not_requested"`
(mode manuel) ou `"pending_manual_entry"` (mode URL) — l'énumération manquante
relevée en A-01 est créée ici et doit être validée.

**Règles appliquées.**

- Montants et taux sérialisés en chaînes décimales (D-35) ; un nombre JSON pour
  un montant est refusé en `VALIDATION_ERROR`.
- Un champ inconnu est stocké `null` avec un motif, jamais `0`, `false` ou `""`
  (PRD §8).
- `price` peut être `null` (« prix sur demande », PRD §11) ; le statut de
  l'opportunité reste `watching`.
- La devise est conservée telle quelle ; la conversion EUR n'est tentée que si un
  taux plus récent que `fx_max_age_hours` existe, sinon les colonnes EUR restent
  `null` et un avertissement est renvoyé — jamais une valeur silencieuse.
- Toute ressource est rattachée au portefeuille du principal (D-29) et filtrée
  par lui.

**Authentification.** D-01 place l'authentification hors du prototype local. Un
`PrincipalProvider` est introduit derrière un port ; l'implémentation de
développement résout un principal unique depuis la configuration. Les codes `401`
et `403` du catalogue sont implémentés et testés, mais l'adaptateur réel viendra
avec D-01. Aucune exposition Internet n'est possible dans cet état, ce qui est
cohérent avec le PRD §6.

### Critères de validation

- [ ] Une Longines L2.257.4.57.6 peut être créée **en mode manuel, sans URL et sans collecteur**, puis retrouvée par `GET`.
- [ ] Une opportunité créée par URL enregistre `canonical_url`, `url_fingerprint` et la plateforme détectée.
- [ ] `price = null` est accepté, persisté à `null`, et aucun montant dérivé n'est produit.
- [ ] Une devise sans taux récent produit les colonnes EUR à `null` plus un avertissement, jamais `0`.
- [ ] La pagination par curseur est stable : insérer une ligne entre deux pages ne duplique ni n'omet d'élément.
- [ ] Une opportunité d'un autre portefeuille renvoie `404`, pas `403` (pas de fuite d'existence).
- [ ] Les fixtures Cartier, Omega et Longines de `test-strategy.md` sont créables ; les champs inconnus y restent `null`.

---

## 7. KAI-102 — Référence, état, set, vendeur et validation (5 pts)

### Contrat

| Méthode | Route | Notes |
|---|---|---|
| `PATCH` | `/api/v1/opportunities/{id}` | correction des champs non historiques |
| `POST` | `/api/v1/opportunities/{id}/identification` | confirmer, corriger ou déclarer la référence inconnue |
| `GET` | `/api/v1/references` | recherche de référence par marque et fragment |

`POST .../identification` est un ajout au contrat (A-02) : l'étape B du parcours
est obligatoire et n'a aucun endpoint. Son corps accepte
`{"action": "confirm" | "correct" | "mark_unknown", "reference_id": …,
"brand": …, "reference": …, "reason": …}` et fait passer
`watches.identification_status` (D-33).

### Normalisation

Les valeurs libres sont converties en vocabulaires fermés, **sans perdre la
donnée brute** (FR-004) : la valeur saisie est conservée dans
`condition_data.raw` / `completeness_data.raw`, la valeur normalisée dans un
champ typé.

| Dimension | Valeurs | Source |
|---|---|---|
| État mécanique | `verified_serviced`, `functional`, `unknown`, `faulty` | `calculation-spec.md` §6 |
| État cosmétique | `excellent`, `very_good`, `good`, `fair`, `poor` | idem |
| Complétude | `full_set`, `box_or_papers`, `watch_only`, `unknown` | idem |
| Originalité | `original`, `uncertain`, `major_modification` | idem |
| Type de vendeur | `private`, `professional`, `unknown` | `platform-rules.md` |

Ces vocabulaires sont dérivés des barèmes de score existants et n'introduisent
aucune règle nouvelle. Le mapping vers les points reste dans le jeu de règles, à
l'Epic 3.

### Validation

Trois niveaux distincts, alignés sur PRD §8 :

1. **Recevable** — l'opportunité peut exister : plateforme et marque suffisent.
2. **Analysable (indicatif)** — référence, prix, devise, état approximatif, set,
   pays. Manque → `GATE_FAILED` avec le détail des champs.
3. **Éligible à `Acheter`** — identité confirmée, etc. Ce niveau est **calculé
   mais non appliqué** dans ce lot : il n'existe pas encore d'analyse.

Le point 3 est exposé en lecture seule sous forme de liste de conditions non
remplies, ce qui donne à KAI-104 de quoi guider la saisie sans anticiper
l'Epic 3.

### Critères de validation

- [ ] Confirmer, corriger et déclarer inconnue une référence produisent trois `identification_status` distincts et trois entrées d'audit.
- [ ] Une référence non confirmée avec `identification_confidence < 80` déclenche `REFERENCE_UNCONFIRMED` sur toute route qui exigerait une valorisation.
- [ ] Une saisie d'état libre inconnue est conservée en brut et normalisée en `unknown`, jamais en une valeur par défaut favorable.
- [ ] Le numéro de série n'apparaît dans aucune réponse d'API par défaut ni dans aucun log.
- [ ] Les trois niveaux de validation sont testés champ par champ.

---

## 8. KAI-103 — Détection des doublons et correction auditée (3 pts)

### Déduplication

Deux clés (D-25) :

1. `(platform_id, external_id)` lorsque l'identifiant externe est connu ;
2. `(platform_id, url_fingerprint)` où l'empreinte est le SHA-256 de l'URL
   canonicalisée.

**Canonicalisation** — schéma et hôte en minuscules, retrait de `www.`, retrait
du fragment, retrait des paramètres de suivi listés en configuration
(`utm_*`, `gclid`, `fbclid`, `ref`, …), tri des paramètres restants, suppression
du `/` final. La liste des paramètres est une donnée de configuration, pas une
constante.

À la création, une collision renvoie `409 OPPORTUNITY_DUPLICATE` avec
l'identifiant existant, conformément au contrat, et propose l'ajout d'une
observation sur l'opportunité existante (PRD §11 : « URL déjà suivie : ouvrir
l'existante, proposer une nouvelle observation »).

Les entrées manuelles sans URL ni identifiant externe ne sont **jamais**
dédupliquées automatiquement : l'index unique est partiel. Un doublon probable
est signalé (même marque, même référence, écart de prix inférieur à un seuil
configurable) mais jamais fusionné sans action utilisateur.

### Correction auditée

`PATCH /opportunities/{id}` : liste blanche explicite des champs corrigeables
(A-03), à valider. Proposition — corrigeables : marque, modèle, référence, état,
set, originalité, pays et type de vendeur, prix courant, devise, notes, stratégie
appliquée. Non corrigeables : toute analyse, toute valorisation, toute
observation, tout événement, tout achat ou vente déjà enregistré.

Chaque correction écrit une ligne dans `audit_log` : acteur, entité, identifiant,
champ, ancienne valeur, nouvelle valeur, motif, `request_id`, horodatage UTC. Le
motif est **obligatoire** pour une correction de référence ou de prix. La table
est en écriture seule (déclencheur de la migration 0012).

### Critères de validation

- [ ] Deux URL différant uniquement par des paramètres de suivi ou une casse d'hôte produisent la même empreinte et donc un `409`.
- [ ] La réponse `409` porte l'identifiant de l'opportunité existante et le code exact du catalogue.
- [ ] Deux saisies manuelles identiques créent deux opportunités distinctes, avec un signalement de doublon probable et aucune fusion.
- [ ] Une correction de référence sans motif est refusée en `VALIDATION_ERROR`.
- [ ] Toute correction produit exactement une ligne d'audit ; un `UPDATE` sur `audit_log` échoue.
- [ ] Une tentative de correction d'un champ historique renvoie une erreur du catalogue, pas un `500`.

---

## 9. Corrections documentaires proposées dans ce lot

À valider ; aucune ne modifie une règle métier.

1. `docs/architecture/overview.md` — ajouter les modules `opportunities`
   (orchestrateur) et `audit` à la liste des huit modules.
2. `docs/architecture/api-contract.md` — ajouter `POST
   /opportunities/{id}/identification`, `GET /opportunities/{id}/events`,
   `GET /jobs/{id}` dans la table des ressources ; documenter l'énumération
   d'`import_status`, le format du curseur, la représentation décimale des
   montants et la liste blanche de `PATCH` ; remplacer l'exemple d'analyse par un
   exemple arithmétiquement cohérent (C-10).
3. `docs/delivery/sprint-01.md` — aligner sur `backlog-v1.md` ou requalifier en
   objectif de release (C-09).
4. `database/schema.sql` — devient un artefact régénéré, avec un en-tête le
   signalant.
5. `docs/product/scoring-engine.md` et `docs/product/gates.md` — à réconcilier
   avant l'Epic 3 (C-01, C-07) ; hors de ce lot.

---

## 10. Plan de tests du lot

| Niveau | Contenu | Emplacement |
|---|---|---|
| Unitaire | `Money` et arrondis ; canonicalisation d'URL ; empreinte de déduplication ; encodage et décodage du curseur ; chargement et empreinte du jeu de règles ; normalisation des vocabulaires ; niveaux de validation ; masquage des logs | `apps/api/tests/unit/` |
| Intégration | migrations aller-retour ; déclencheurs d'immuabilité ; contrainte d'exclusion des `platform_rules` ; idempotence de la seed ; dépôts ; toutes les routes du lot sur PostgreSQL réel | `apps/api/tests/integration/` |
| Contrat | instantané `openapi.json` ; un test par code d'erreur du catalogue vérifiant statut et enveloppe | `apps/api/tests/contract/` |
| Fixtures | Cartier 590003, Omega, Longines L2.257.4.57.6 en JSON, chargeables par l'API, champs inconnus à `null` | `tests/fixtures/` |
| Propriétés | à données identiques, réponse identique (hors `request_id` et horodatages) ; aucun montant `NaN` ou infini ; aucune valeur par défaut silencieuse sur un champ inconnu | `apps/api/tests/unit/` |

Les propriétés de `test-strategy.md` portant sur la valorisation, le pricing et
le score ne sont pas testables dans ce lot : les moteurs n'existent pas. Elles
sont listées comme dettes explicites, non comme couverture manquante.

**Aucun test n'effectue d'appel réseau sortant.** Les taux de change utilisent un
adaptateur en mémoire (D-03).

---

## 11. Definition of Done, story par story

| Critère `CLAUDE.md` | 001 | 002 | 003 | 101 | 102 | 103 |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Migration, modèle et contrat cohérents | s.o. | s.o. | ✔ | ✔ | ✔ | ✔ |
| Tests nominal et limites | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Calculs reproductibles avec fixtures | s.o. | s.o. | s.o. | ✔ | ✔ | ✔ |
| Erreurs issues du catalogue | s.o. | ✔ | ✔ | ✔ | ✔ | ✔ |
| Logs sans secret ni donnée inutile | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Documentation mise à jour | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Format, typage, lint et tests verts en CI | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |

Une story dont une case reste vide n'est pas déclarée terminée.

---

## 12. Séquencement et commandes de validation

Ordre : 001 → 002 → 003 → 101 → 102 → 103. Les stories 101 à 103 partagent la
même surface d'API ; le contrat OpenAPI n'est figé qu'à la fin de 103.

```bash
make bootstrap        # dépendances API et web
make up               # postgres, redis, api, web
make migrate          # alembic upgrade head + seed plateformes
make fmt lint typecheck
make test             # unitaires + intégration + contrats, avec couverture
make contracts        # regénère openapi.json et les types TS, échoue si diff
make check            # tout ce qui précède, identique à la CI
```

---

## 13. Limites connues à l'issue du lot

- Aucun moteur de valorisation, de pricing ni de scoring : `latest_analysis` vaut
  toujours `null` et aucun verdict n'est produit.
- Aucun collecteur ; `access_method` reste `manual` pour toutes les plateformes.
- Aucune valeur de commission n'est seedée ; le pricing sera bloqué tant que
  D-26 n'est pas tranchée.
- Aucune authentification réelle (D-01) : la pile ne doit pas être exposée.
- Aucun capital de portefeuille (D-22) : `GET /portfolio/summary` n'est pas livré.
- Le worker Redis démarre mais n'exécute aucune tâche : aucune surveillance.
- Les enchères ne sont pas modélisées finement (S-15), reporté à l'Epic 4.
- Les questions D-11 à D-22 restent ouvertes et bloquent les Epics 2, 3 et 5.
