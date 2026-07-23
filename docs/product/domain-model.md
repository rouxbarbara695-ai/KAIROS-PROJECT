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

User
└── Portfolio
    └── Opportunity
        ├── Listing
        ├── Watch
        ├── Market
        ├── Pricing
        └── Scoring

Listing
├── Seller
└── Marketplace

Watch
└── Reference

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
