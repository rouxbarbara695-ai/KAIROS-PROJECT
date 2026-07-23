# Scoring Engine

**Version :** 1.0  
**Statut :** Stable  
**Dernière mise à jour :** 23 juillet 2026

---

# Purpose

The Scoring Engine is the core decision engine of Kairos.

Its objective is not to estimate the value of a watch.

Its objective is to determine whether purchasing a specific watch represents a good investment opportunity for a given user, considering:

- current market conditions;
- the user's available capital;
- the user's existing inventory;
- expected profitability;
- expected liquidity;
- investment risk.

The engine outputs:

- Kairos Score (/100)
- Maximum Purchase Price
- Expected Selling Price
- Expected Time to Sell
- Recommendation (Buy / Watch / Pass)

---

# Philosophy

Kairos does not evaluate watches.

Kairos evaluates opportunities.

The exact same watch may receive different scores depending on:

- available capital;
- current inventory;
- portfolio diversification;
- investment strategy.

The Kairos Score is therefore contextual and personalized.

---

# Engine Workflow

The scoring engine operates in two consecutive phases.

```
Listing
    │
    ▼
Eligibility Gates
    │
    ▼
Scoring Engine
    │
    ▼
Decision Engine
```

A listing cannot be scored until every eligibility gate has been validated.

---

# Phase 0 — Eligibility Gates

Eligibility Gates prevent Kairos from scoring opportunities that should never be considered.

If a Gate fails, the process stops immediately.

No Kairos Score is calculated.

---

## G1 — Authenticity

Kairos immediately rejects a listing if there is a significant authenticity risk.

Examples include:

- suspected counterfeit;
- inconsistent reference;
- inconsistent serial numbers;
- major non-original components;
- suspicious provenance.

Result:

```
PASS

Reason:
Authenticity cannot be reasonably guaranteed.
```

---

## G2 — Data Quality

The listing must contain enough information to perform a reliable analysis.

Minimum requirements include:

- identifiable reference;
- usable photographs;
- sufficient listing information.

Otherwise:

```
Analysis impossible
```

---

## G3 — Supported Market

Kairos only analyzes watches for which a sufficiently documented secondary market exists.

Examples of unsupported cases:

- extremely rare prototypes;
- unique custom pieces;
- markets with insufficient comparable sales.

---

# Phase 1 — Kairos Score

The Kairos Score is composed of five independent pillars.

Each pillar contributes to the final score using predefined weights.

---

# 1. Profitability (30%)

Measures expected financial return.

### Sub-criteria

- Expected Profit (€) → 60%
- Return on Capital (%) → 40%

---

# 2. Liquidity (27.5%)

Measures how quickly and reliably capital can be recovered.

### Sub-criteria

- Expected Time to Sell → 50%
- Market Depth → 25%
- Market Consistency → 25%

---

# 3. Capital & Portfolio Allocation (20%)

Measures whether purchasing the watch is an efficient use of capital.

### Sub-criteria

- Cash Impact → 40%
- Portfolio Diversification → 30%
- Current Capital Immobilization → 30%

---

# 4. Watch Condition (15%)

Measures the technical quality of the asset.

### Sub-criteria

- Mechanical Condition → 40%
- Cosmetic Condition → 35%
- Completeness (box, papers, accessories) → 20%

Authenticity is intentionally excluded from this pillar.

It is evaluated before scoring through Eligibility Gates.

---

# 5. Estimation Confidence (7.5%)

Measures how trustworthy Kairos' own analysis is.

### Sub-criteria

- Listing Data Quality → 35%
- Comparable Sales Quality → 30%
- Seller Reliability → 20%
- Marketplace Guarantees → 15%

---

# Dependency Rules

The Kairos Score is not a simple weighted average.

Certain criteria influence others.

---

## D1

Portfolio diversification only creates value if the watch has sufficient liquidity.

---

## D2

Estimation confidence depends on market depth.

---

## D3

High profitability cannot compensate for excessive capital immobilization.

---

## D4

The larger the capital allocation, the stricter Kairos becomes regarding every other criterion.

---

## D5

Low estimation confidence caps the maximum achievable Kairos Score.

---

## D6

Seller reputation and marketplace guarantees only improve confidence.

They never improve profitability.

---

## D7

High seller risk may trigger an Eligibility Gate before scoring begins.

---

# Design Principles

The scoring engine follows several guiding principles.

- Conservative when uncertainty is high.
- Personalized rather than universal.
- Opportunity-focused rather than watch-focused.
- Explainable.
- Modular.
- Continuously improvable.

Every recommendation produced by Kairos must be explainable through measurable criteria.

No hidden decision should exist inside the engine.
