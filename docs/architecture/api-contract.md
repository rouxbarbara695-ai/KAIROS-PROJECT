# Contrat API V1

Base `/api/v1`. JSON UTF-8. Authentification Bearer en environnement exposé.
Chaque réponse possède `request_id`. Pagination par curseur, limite 20 par
défaut, 100 maximum. Les écritures financières acceptent `Idempotency-Key`.

## Ressources

| Méthode | Route | Fonction |
|---|---|---|
| POST | `/opportunities` | créer par URL ou saisie |
| GET | `/opportunities` | lister/filtrer |
| GET | `/opportunities/{id}` | détail et dernière analyse |
| PATCH | `/opportunities/{id}` | corriger données non historiques |
| POST | `/opportunities/{id}/observations` | ajouter observation |
| POST | `/opportunities/{id}/comparables` | ajouter comparable |
| PATCH | `/comparables/{id}` | corriger/exclure avec motif |
| POST | `/opportunities/{id}/analyses` | recalculer |
| GET | `/opportunities/{id}/analyses` | historique immuable |
| POST | `/opportunities/{id}/transitions` | changer le pipeline |
| POST | `/opportunities/{id}/costs` | coût prévu/réel |
| POST | `/opportunities/{id}/sale-listings` | mise en vente |
| POST | `/opportunities/{id}/sales` | vente/encaissement |
| GET | `/portfolio/summary` | cash, stock, encours, performance |
| GET | `/alerts` | alertes |
| PATCH | `/alerts/{id}` | lu/archivé |
| GET | `/platforms/{code}/rules` | règle applicable |

## Exemple création

```json
{
  "source": {"mode": "url", "url": "https://example.test/listing/123"},
  "listing": {"platform_code": "chrono24", "price": "1800.00", "currency": "EUR"},
  "watch": {
    "brand": "Longines",
    "reference": "L2.257.4.57.6",
    "condition": "like_new",
    "box": true,
    "papers": true
  },
  "seller": {"country_code": "FR", "type": "private"}
}
```

Retour `201` avec `id`, `status=watching`, `import_status` et liens. Si l’URL
existe : `409 OPPORTUNITY_DUPLICATE` avec l’identifiant existant.

## Exemple d’analyse

```json
{
  "analysis_id": "uuid",
  "rules_version": "1.0",
  "calculated_at": "2026-07-28T12:00:00Z",
  "gates": [{"code": "G1", "status": "passed", "reasons": []}],
  "valuation": {
    "low": "1650.00", "central": "1800.00", "high": "1950.00",
    "currency": "EUR", "confidence": "72.00"
  },
  "pricing": {
    "max_purchase_price": "1325.00",
    "expected_sale_price": "1800.00",
    "expected_profit": "275.00",
    "expected_roi": "0.1800",
    "expected_days_to_sell": 45
  },
  "score": {
    "total": "78.50",
    "pillars": {"profitability": "82.00", "liquidity": "70.00"},
    "caps": []
  },
  "recommendation": "buy",
  "decision_reasons": ["Prix inférieur au maximum de 125 €"]
}
```

## Erreurs

```json
{
  "error": {
    "code": "VALUATION_INSUFFICIENT_COMPARABLES",
    "message": "Au moins deux comparables recevables sont nécessaires.",
    "field": null,
    "details": {"eligible": 1, "required": 2},
    "request_id": "uuid"
  }
}
```

Codes : `VALIDATION_ERROR` 422, `UNAUTHORIZED` 401, `FORBIDDEN` 403,
`NOT_FOUND` 404, `OPPORTUNITY_DUPLICATE` 409, `INVALID_TRANSITION` 409,
`REFERENCE_UNCONFIRMED` 422, `GATE_FAILED` 422,
`VALUATION_INSUFFICIENT_COMPARABLES` 422, `FX_RATE_UNAVAILABLE` 503,
`COLLECTOR_UNAVAILABLE` 503, `RULE_VERSION_MISSING` 500.

## Asynchronisme

Un import retourne `202` avec `job_id`. `GET /jobs/{id}` retourne
`queued|running|succeeded|failed|partial`. Une relance utilise la même clé
d’idempotence. Une collecte partielle conserve chaque résultat réussi et liste
les sources en échec.
