# Opportunity Analysis Engine

**Version:** 1.0  
**Status:** Validated  
**Last updated:** 23 July 2026

---

# Purpose

The Opportunity Analysis Engine is the entry point of Kairos.

Its purpose is to transform a watch listing selected by the user into a structured, enriched and continuously monitored investment opportunity.

KAIROS starts with user-submitted listings, then progressively adds saved
searches and automated opportunity discovery. Monitoring and automatic
re-evaluation are core target capabilities, not optional extensions.

---

# V1 Operating Model

## Manual opportunity selection

In V1, the user identifies a potentially interesting listing and submits its URL to Kairos.

This manual selection acts as the first relevance filter.

Kairos therefore avoids processing large volumes of listings that do not match the user's investment strategy.

---

## Automated analysis

Once the URL is submitted, Kairos automatically:

- extracts the listing data;
- identifies the watch and its reference;
- normalizes the information;
- retrieves comparable listings and transactions;
- enriches missing technical information;
- evaluates data reliability;
- stores the opportunity;
- calculates the Kairos Score;
- calculates the pricing strategy;
- monitors the listing and its market over time.

The manual process ends when the user submits the URL.

---

# Data Collection Strategy

Kairos collects several types of market information.

## Active listings

Examples:

- asking price;
- listing date;
- price changes;
- seller type;
- seller location;
- condition;
- completeness;
- marketplace guarantees.

Active listings indicate current market supply but do not prove the final transaction price.

---

## Confirmed transaction prices

A transaction price is considered confirmed when the final selling price is explicitly observable.

Examples:

- completed auctions;
- purchases recorded directly by a Kairos user;
- trusted data providers exposing transaction data.

Confirmed transactions receive the highest confidence level.

---

## Estimated market prices

Estimated prices may come from specialized market-data providers.

These estimates are useful but must remain distinguishable from confirmed transactions.

---

## Last observed asking price

When a listing disappears, Kairos may retain its last observed asking price.

This does not prove that the watch was sold or that the final transaction occurred at that price.

Kairos must never present this value as a confirmed selling price.

---

# Comparable Data Confidence

Each comparable must include a source type and confidence level.

Suggested classification:

- **Level A — Confirmed transaction**
- **Level B — Trusted market estimate**
- **Level C — Active comparable listing**
- **Level D — Last observed price before disappearance**
- **Level E — Unverified or incomplete data**

The confidence level directly affects the Estimation Confidence pillar of the Kairos Score.

---

# Monitoring

After an opportunity is created, Kairos continues monitoring relevant data.

Possible events include:

- listing price changed;
- listing sold publicly;
- listing removed;
- listing status unknown;
- new comparable listed;
- comparable sold;
- market estimate updated.

Significant events may trigger:

- a new market-value estimate;
- a recalculated Kairos Score;
- an updated maximum purchase price;
- an updated selling strategy;
- a user notification.

---

# Data Retention

Kairos does not need to preserve every raw element indefinitely.

## Permanent structured data

Kairos should retain the information required for market intelligence and historical analysis, including:

- marketplace and listing identifier;
- watch reference;
- observed price;
- observation date;
- listing status;
- condition;
- completeness;
- seller category;
- geographical area;
- comparable type;
- confidence level;
- Kairos estimates;
- final outcome when known.

## Optional or temporary raw data

Heavy or legally sensitive elements may be stored temporarily or referenced rather than permanently retained.

Examples:

- full listing descriptions;
- original images;
- raw webpage content.

The retention policy must prioritize useful structured data over indiscriminate storage.

---

# Product Principle

Kairos V1 follows a hybrid model:

> The user selects the opportunity. Kairos automates the intelligence.

This model combines:

- human relevance filtering;
- automated data acquisition;
- scalable historical data accumulation;
- lower technical and storage complexity;
- progressive preparation for future market-wide automation.

---

# Future Evolution

Once Kairos has validated its analysis rules and accumulated sufficient data, the system may progressively automate opportunity discovery.

Possible stages:

1. Manual URL submission.
2. Automated monitoring of saved searches.
3. Automatic preselection of high-potential listings.
4. Large-scale autonomous market scanning.

Full market-wide discovery is an evolution of the V1. Monitoring submitted
listings, updating valuations and recalculating decisions are part of the
product’s essential scope from the outset.
