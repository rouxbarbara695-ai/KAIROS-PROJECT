from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CHAR, Boolean, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base
from app.shared.infrastructure.db.models.enums import (
    ListingStatus,
    PriceKind,
    SourceReliabilityLevel,
    pg_enum,
)


class Comparable(Base):
    __tablename__ = "comparables"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watch_references.id"), nullable=False
    )
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id")
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_external_id: Mapped[str | None] = mapped_column(Text)
    seller_fingerprint: Mapped[str | None] = mapped_column(Text)
    price_kind: Mapped[str] = mapped_column(
        pg_enum(PriceKind, "price_kind"), nullable=False
    )
    amount_source: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    amount_eur: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    rate_to_eur: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    fx_rate_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    fx_source: Mapped[str] = mapped_column(Text, nullable=False)
    fx_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fx_rates.id")
    )
    buyer_variable_fee_eur: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, server_default=text("0")
    )
    buyer_fixed_fee_eur: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, server_default=text("0")
    )
    compulsory_shipping_eur: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, server_default=text("0")
    )
    buyer_total_price_eur: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False
    )
    market_status: Mapped[str] = mapped_column(
        pg_enum(ListingStatus, "listing_status"), nullable=False
    )
    listed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    source_reliability: Mapped[str] = mapped_column(
        pg_enum(SourceReliabilityLevel, "source_reliability_level"), nullable=False
    )
    condition_data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    completeness_data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    raw_data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class ComparableOverride(Base):
    __tablename__ = "comparable_overrides"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    comparable_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comparables.id"), nullable=False
    )
    previous_override_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comparable_overrides.id"), unique=True
    )
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    corrected_data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class MarketValuation(Base):
    __tablename__ = "market_valuations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    ruleset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rulesets.id"), nullable=False
    )
    calculated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    low_value_eur: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    central_value_eur: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    high_value_eur: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    valuation_confidence: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    trend: Mapped[str | None] = mapped_column(Text)
    ruleset_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class ValuationComparable(Base):
    __tablename__ = "valuation_comparables"

    valuation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market_valuations.id"), primary_key=True
    )
    comparable_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comparables.id"), primary_key=True
    )
    source_amount_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False
    )
    source_currency_snapshot: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    amount_eur_snapshot: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    buyer_total_price_eur: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False
    )
    comparable_set_premium: Mapped[Decimal] = mapped_column(
        Numeric(18, 10), nullable=False
    )
    target_set_premium: Mapped[Decimal] = mapped_column(Numeric(18, 10), nullable=False)
    adjusted_price_eur: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    source_reliability_factor: Mapped[Decimal] = mapped_column(
        Numeric(18, 12), nullable=False
    )
    recency_factor: Mapped[Decimal] = mapped_column(Numeric(18, 12), nullable=False)
    reference_factor: Mapped[Decimal] = mapped_column(Numeric(18, 12), nullable=False)
    condition_factor: Mapped[Decimal] = mapped_column(Numeric(18, 12), nullable=False)
    completeness_factor: Mapped[Decimal] = mapped_column(
        Numeric(18, 12), nullable=False
    )
    seller_independence_factor: Mapped[Decimal] = mapped_column(
        Numeric(18, 12), nullable=False
    )
    final_weight: Mapped[Decimal] = mapped_column(Numeric(24, 16), nullable=False)
    anomaly_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    excluded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    trace: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
