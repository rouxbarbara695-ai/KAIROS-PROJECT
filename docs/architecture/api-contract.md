# Contrat API V1

Base `/api/v1`, JSON UTF-8, Bearer hors local. Toute réponse porte
`X-Request-Id`. Tous les timestamps sont ISO 8601 UTC.

## Conventions

### Décimaux

Montants, taux, ROI et scores sont des chaînes décimales JSON :

```json
{
  "amount": "1800.00",
  "currency": "EUR",
  "amount_eur": "1800.00",
  "rate_to_eur": "1.00000000",
  "fx_rate_at": "2026-07-28T10:00:00Z",
  "fx_source": "identity"
}
```

Jamais de nombre flottant JSON pour ces champs.

### Pagination

Ordre par défaut : `created_at DESC, id DESC`. `next_cursor` est un Base64URL
opaque encodant `{"created_at":"...","id":"uuid"}`. Le serveur valide la forme
mais le client ne l’interprète pas. `limit=20`, maximum 100.

### Concurrence

Les réponses modifiables exposent `ETag: "version-n"`. `PATCH` exige
`If-Match`. Un conflit retourne `409 RESOURCE_VERSION_CONFLICT`.

### Idempotence

`POST` de création, transitions et écritures financières acceptent
`Idempotency-Key` (1–128 caractères). Même clé + même empreinte retourne la
réponse initiale ; même clé + charge différente retourne
`409 IDEMPOTENCY_CONFLICT`.

### Limitation de débit

`POST /auth/login` est la seule route publique de l’API. Les échecs y sont
comptés par adresse IP d’origine et par adresse électronique, sur une fenêtre
glissante de cinq minutes. Au-delà du seuil, la route retourne
`429 RATE_LIMITED` avec `details.retry_after_seconds`, **avant** toute
vérification de mot de passe : Argon2 est lent par construction, et laisser un
attaquant déclencher ce calcul lui offrirait le déni de service que la
limitation doit empêcher.

Le seuil par adresse électronique est délibérément beaucoup plus haut que celui
par adresse IP. KAIROS est mono-organisation : une limite serrée par adresse
donnerait à n’importe qui le moyen d’enfermer le propriétaire dehors en
martelant la sienne.

Une connexion réussie remet les compteurs à zéro. Si le compteur est
injoignable, la connexion reste possible et l’incident est journalisé : la
frontière de sécurité est le mot de passe, pas le limiteur.

## Ressources

| Méthode | Route | Fonction |
|---|---|---|
| POST | `/opportunities` | créer en mode manuel ou URL |
| GET | `/opportunities` | lister/filtrer |
| GET | `/opportunities/{id}` | détail et dernière analyse |
| PATCH | `/opportunities/{id}` | corriger les champs autorisés avec motif |
| POST | `/opportunities/{id}/reference-confirmations` | confirmer/corriger/inconnue |
| PATCH | `/opportunities/{id}/watch-profile` | corriger état/set avec audit |
| PATCH | `/opportunities/{id}/seller-profile` | corriger vendeur/pays avec audit |
| POST | `/opportunities/{id}/price-inputs` | ajouter prix manuel/enchère daté |
| GET | `/opportunities/{id}/events` | historique métier et audit |
| POST | `/opportunities/{id}/observations` | observation manuelle |
| POST | `/opportunities/{id}/comparables` | ajouter comparable |
| POST | `/comparables/{id}/overrides` | corriger/exclure/réintégrer avec motif |
| POST | `/opportunities/{id}/analyses` | créer/recalculer |
| GET | `/opportunities/{id}/analyses` | historique immuable |
| GET | `/analyses/{id}` | détail et traces |
| POST | `/opportunities/{id}/transitions` | changer le pipeline |
| POST | `/opportunities/{id}/costs` | coût prévu/réel |
| POST | `/opportunities/{id}/purchases` | enregistrer achat |
| POST | `/opportunities/{id}/sale-listings` | mise en vente |
| POST | `/opportunities/{id}/sales` | vente |
| POST | `/portfolio/ledger-entries` | apport/retrait/mouvement |
| GET | `/portfolio/summary` | cash, encours, stock, performance |
| GET/POST | `/strategies` | stratégies et versions |
| GET | `/rulesets/{version}` | ruleset immuable |
| GET | `/platforms/{code}/rules` | règle applicable à date/région |
| GET | `/alerts` | alertes |
| PATCH | `/alerts/{id}` | marquer lue/archivée |
| GET | `/jobs/{id}` | état d’un job autorisé |

## Création manuelle

```json
{
  "portfolio_id": "uuid",
  "source": {
    "mode": "manual",
    "manual_identifier": "LONGINES-2026-001"
  },
  "watch": {
    "brand": "Longines",
    "reference": "L2.257.4.57.6",
    "reference_status": "unconfirmed",
    "mechanical_condition": "functional",
    "cosmetic_condition": "like_new",
    "box": true,
    "papers": true
  },
  "seller": {
    "country_code": "FR",
    "seller_type": "private"
  },
  "price": {
    "amount": "1800.00",
    "currency": "EUR"
  }
}
```

Retour synchrone `201` avec `id`, `source.mode=manual`, `status=watching`,
`version=1`. Il n’existe pas d’`import_status` pour le mode manuel.

Création URL : `source.mode=url`, `url`. Retour `201` si seule l’URL est stockée
pour saisie manuelle ; `202` avec `job_id` seulement si un import autorisé est
effectivement lancé.

Doublons : `409 OPPORTUNITY_DUPLICATE` avec `existing_opportunity_id` et
`matched_on=canonical_url|external_id|manual_identifier`.

## Correction

`PATCH /opportunities/{id}` autorise uniquement : statut courant non financier,
stratégie sélectionnée et données de présentation. Référence, montre, vendeur,
prix, état, set et données financières utilisent leurs commandes dédiées. Toute
correction exige `reason`.

Les corrections `watch-profile` et `seller-profile` modifient la projection
courante, conservent le brut d’origine et écrivent obligatoirement un
`audit_event` avec `before_data`, `after_data`, auteur et motif dans la même
transaction.

## Confirmation de référence

```json
{
  "status": "corrected",
  "reference_id": "uuid",
  "reason": "Référence visible sur les papiers"
}
```

Statuts : `suggested|confirmed|corrected|unknown`. Une nouvelle confirmation ne
réécrit pas l’événement précédent.

## Analyse complète

```json
{
  "analysis_id": "uuid",
  "previous_analysis_id": null,
  "ruleset_version": "1.0.0",
  "strategy_version_id": "uuid",
  "platform_rule_id": "uuid",
  "calculated_at": "2026-07-28T12:00:00Z",
  "published_at": "2026-07-28T12:00:01Z",
  "current_price_eur": "1200.00",
  "gates": [
    {"code": "G1_AUTHENTICITY", "status": "passed", "reason_codes": []},
    {"code": "G2_IDENTIFICATION", "status": "passed", "reason_codes": []},
    {"code": "G3_DATA_QUALITY", "status": "passed", "reason_codes": []},
    {"code": "G4_MARKET_SUPPORT", "status": "passed", "reason_codes": []},
    {"code": "G5_SELLER_RISK", "status": "passed", "reason_codes": []}
  ],
  "valuation": {
    "low_eur": "1650.00",
    "central_eur": "1800.00",
    "high_eur": "1950.00",
    "valuation_confidence": "72.00"
  },
  "scenarios": {
    "prudent": {
      "sale_price_eur": "1650.00",
      "total_cost_eur": "1290.00",
      "net_sale_proceeds_eur": "1570.00",
      "profit_eur": "280.00",
      "roi": "0.21705426"
    },
    "central": {
      "sale_price_eur": "1800.00",
      "total_cost_eur": "1275.00",
      "net_sale_proceeds_eur": "1710.00",
      "profit_eur": "435.00",
      "roi": "0.34117647"
    },
    "favorable": {
      "sale_price_eur": "1950.00",
      "total_cost_eur": "1260.00",
      "net_sale_proceeds_eur": "1850.00",
      "profit_eur": "590.00",
      "roi": "0.46825397"
    }
  },
  "pricing": {
    "raw_max_purchase_price_eur": "1334.72",
    "max_purchase_price_eur": "1330.00",
    "binding_constraint": "minimum_profit",
    "expected_sale_price_eur": "1800.00",
    "expected_profit_eur": "435.00",
    "expected_roi": "0.34117647",
    "expected_days_to_sell": 45
  },
  "score": {
    "raw_total": "78.5000",
    "total": "78.50",
    "pillars": {
      "profitability": "82.00",
      "liquidity": "70.00",
      "portfolio": "76.00",
      "condition": "90.00",
      "evidence_quality": "68.00"
    },
    "caps": []
  },
  "recommendation": "buy",
  "decision_reasons": [
    {
      "code": "PRICE_BELOW_MAXIMUM",
      "message": "Le prix courant est inférieur de 130,00 € au maximum prudent.",
      "impact_eur": "130.00"
    }
  ]
}
```

Les nombres de cet exemple illustrent la **forme du contrat**, pas une fixture
arithmétique. Les fixtures faisant foi sont dans la stratégie de tests.

## Analyse impossible

Une réponse publiée peut contenir `recommendation=analysis_impossible`,
`valuation=null`, `scenarios=null`, `pricing=null`, `score=null`, avec les portes
et raisons d’échec. Elle est persistée comme toute autre analyse.

## Erreurs

| Code | HTTP | Usage |
|---|---:|---|
| `VALIDATION_ERROR` | 422 | champ invalide |
| `UNAUTHORIZED` / `FORBIDDEN` | 401 / 403 | accès |
| `NOT_FOUND` | 404 | ressource absente dans le portefeuille |
| `OPPORTUNITY_DUPLICATE` | 409 | clé déjà suivie |
| `IDEMPOTENCY_CONFLICT` | 409 | même clé, autre charge |
| `RESOURCE_VERSION_CONFLICT` | 409 | `If-Match` obsolète |
| `IMMUTABLE_RESOURCE` | 409 | modification d’un historique |
| `INVALID_TRANSITION` | 409 | pipeline interdit |
| `REFERENCE_UNCONFIRMED` | 422 | analyse non autorisée |
| `GATE_FAILED` | 422 | commande exigeant portes passées |
| `VALUATION_INSUFFICIENT_COMPARABLES` | 422 | moins de 2 |
| `FX_RATE_UNAVAILABLE` | 503 | taux absent/expiré |
| `COLLECTOR_NOT_AUTHORIZED` | 403 | mode d’accès non validé |
| `COLLECTOR_UNAVAILABLE` | 503 | échec externe |
| `RATE_LIMITED` | 429 | trop de tentatives |
| `RULESET_MISSING` | 500 | version non résolue |

Format :

```json
{
  "error": {
    "code": "RESOURCE_VERSION_CONFLICT",
    "message": "La ressource a été modifiée.",
    "field": null,
    "details": {"current_version": 3},
    "request_id": "uuid"
  }
}
```

## Jobs

`GET /jobs/{id}` retourne
`queued|running|succeeded|failed|partial`, tentatives et erreurs par source. Une
relance conserve la clé d’idempotence ; chaque succès partiel est conservé.
