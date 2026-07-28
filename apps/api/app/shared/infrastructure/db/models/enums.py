"""Types énumérés PostgreSQL — miroir exact de database/schema.sql.

Les types sont créés par la migration SQL (`create type ...`), donc chaque
`postgresql.ENUM` est déclaré avec `create_type=False` pour qu'Alembic/
SQLAlchemy ne tente pas de le recréer.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy.dialects import postgresql


class ListingStatus(StrEnum):
    ACTIVE = "active"
    SOLD = "sold"
    REMOVED = "removed"
    ENDED = "ended"
    UNKNOWN = "unknown"


class PriceKind(StrEnum):
    ASKING = "asking"
    OFFER = "offer"
    ACCEPTED_OFFER = "accepted_offer"
    CURRENT_BID = "current_bid"
    HAMMER = "hammer"
    REALIZED = "realized"
    EXTERNAL_ESTIMATE = "external_estimate"
    KAIROS_ESTIMATE = "kairos_estimate"


class OpportunitySourceMode(StrEnum):
    MANUAL = "manual"
    URL = "url"
    ASSISTED_IMPORT = "assisted_import"
    CONNECTOR = "connector"


class OpportunityStatus(StrEnum):
    WATCHING = "watching"
    BUY = "buy"
    AUCTION = "auction"
    PURCHASED = "purchased"
    IN_STOCK = "in_stock"
    LISTED_FOR_SALE = "listed_for_sale"
    AWAITING_BUYER_PAYMENT = "awaiting_buyer_payment"
    AWAITING_PAYOUT = "awaiting_payout"
    SOLD = "sold"
    ABANDONED = "abandoned"


class Recommendation(StrEnum):
    BUY = "buy"
    WATCH = "watch"
    PASS = "pass"
    ANALYSIS_IMPOSSIBLE = "analysis_impossible"


class SourceReliabilityLevel(StrEnum):
    A = "a"
    B = "b"
    C = "c"
    D = "d"
    E = "e"


class ReferenceConfirmationStatus(StrEnum):
    UNCONFIRMED = "unconfirmed"
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    UNKNOWN = "unknown"


class GateStatus(StrEnum):
    PASSED = "passed"
    PASSED_WITH_WARNING = "passed_with_warning"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


class AnalysisState(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class CostStatus(StrEnum):
    PROJECTED = "projected"
    ACTUAL = "actual"


class CostPhase(StrEnum):
    ACQUISITION = "acquisition"
    PREPARATION = "preparation"
    SALE = "sale"


class CostCalculationMode(StrEnum):
    FIXED = "fixed"
    RATE = "rate"


class CostBasis(StrEnum):
    PURCHASE_PRICE = "purchase_price"
    SALE_PRICE = "sale_price"


class CostKind(StrEnum):
    BUYER_FEE = "buyer_fee"
    SELLER_FEE = "seller_fee"
    SHIPPING_IN = "shipping_in"
    SHIPPING_OUT = "shipping_out"
    INSURANCE = "insurance"
    CUSTOMS = "customs"
    ACQUISITION_TAX = "acquisition_tax"
    SALE_TAX = "sale_tax"
    FX = "fx"
    AUTHENTICATION = "authentication"
    SERVICE = "service"
    REPAIR = "repair"
    BATTERY = "battery"
    POLISHING = "polishing"
    ACCESSORY = "accessory"
    PACKAGING = "packaging"
    OTHER = "other"


class PlatformAccessMethod(StrEnum):
    MANUAL = "manual"
    ASSISTED_IMPORT = "assisted_import"
    OFFICIAL_API = "official_api"
    PARTNER = "partner"


class LedgerEntryKind(StrEnum):
    CAPITAL_CONTRIBUTION = "capital_contribution"
    WITHDRAWAL = "withdrawal"
    PURCHASE_PAYMENT = "purchase_payment"
    COST_PAYMENT = "cost_payment"
    SALE_RECEIPT = "sale_receipt"
    REFUND = "refund"
    POSITIVE_ADJUSTMENT = "positive_adjustment"
    NEGATIVE_ADJUSTMENT = "negative_adjustment"


def pg_enum(enum_cls: type[StrEnum], name: str) -> postgresql.ENUM:
    return postgresql.ENUM(
        *[member.value for member in enum_cls],
        name=name,
        create_type=False,
    )
