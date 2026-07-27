# Domain Model

## Purpose

The Domain Model defines the core business objects of Kairos.

It establishes:
- what exists in the system;
- the responsibility of each object;
- how they relate to each other.

This document is the single source of truth for the business architecture of Kairos.

---

# Architecture Principles

## Single Responsibility

Each object has one business responsibility.

## Single Source of Truth

Each piece of information has one owner.

## Orchestration

The Opportunity coordinates the analysis but performs no business calculations.

## Independent Evolution

Each business expertise can evolve independently without affecting the overall architecture.

---

# Domain Map

User owns a Portfolio and creates Opportunities.

An Opportunity points to one Listing and accumulates immutable Analyses.

A Listing:

- belongs to one Marketplace;
- may belong to one Seller;
- describes one Watch;
- accumulates Listing Observations.

A Watch may be identified as one Reference.

An Analysis uses one Market Valuation and produces Pricing, Scoring and a
Recommendation. A Market Valuation is supported by weighted Comparables.

Monitoring creates observations and events. Significant events trigger new
analyses and may create Alerts.

---

# Business Objects

## User

Represents the investor using Kairos.

---

## Portfolio

Represents the user's investment portfolio.

Responsible for capital allocation, holdings and portfolio performance.

---

## Opportunity

Represents one investment decision.

It orchestrates the complete analysis.

---

## Listing

Represents one marketplace advertisement.

Contains only marketplace information.

---

## Watch

Represents the physical watch being analysed.

---

## Reference

Represents the technical knowledge associated with a watch reference.

---

## Seller

Represents the person or business selling the watch.

---

## Marketplace

Represents the platform hosting the listing.

---

## Market

Represents the aggregated market intelligence used for valuation.

---

## Pricing

Represents the pricing engine output.

---

## Scoring

Represents the scoring engine output.

---

## Listing Observation

Represents the state of a listing at a precise time. Observations are append-only
and preserve price, currency, availability, freshness and collection status.

---

## Comparable

Represents one market data point. It explicitly distinguishes asking prices,
realized prices and external estimates.

---

## Market Valuation

Represents a dated low, central and high market estimate together with its
comparables, weights, confidence and calculation rules.

---

## Analysis

Represents an immutable decision snapshot. It records gates, valuation, pricing,
score, recommendation, trigger and rules version.

---

## Platform Rule

Represents fees, logistics and conditions applicable to one marketplace during
a defined period.

---

## Alert

Represents a meaningful decision event. Alerts are not emitted for every raw
change.
