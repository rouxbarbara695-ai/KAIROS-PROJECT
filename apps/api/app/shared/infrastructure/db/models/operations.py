from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base
from app.shared.infrastructure.db.models.enums import (
    CostBasis,
    CostCalculationMode,
    CostKind,
    CostPhase,
    CostStatus,
    ListingStatus,
    pg_enum,
)


class OpportunityCost(Base):
    __tablename__ = "opportunity_costs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id")
    )
    phase: Mapped[str] = mapped_column(pg_enum(CostPhase, "cost_phase"), nullable=False)
    kind: Mapped[str] = mapped_column(pg_enum(CostKind, "cost_kind"), nullable=False)
    status: Mapped[str] = mapped_column(
        pg_enum(CostStatus, "cost_status"), nullable=False
    )
    calculation_mode: Mapped[str] = mapped_column(
        pg_enum(CostCalculationMode, "cost_calculation_mode"), nullable=False
    )
    basis: Mapped[str | None] = mapped_column(pg_enum(CostBasis, "cost_basis"))

    amount_low_source: Mapped[float | None] = mapped_column(Numeric(16, 2))
    amount_central_source: Mapped[float | None] = mapped_column(Numeric(16, 2))
    amount_high_source: Mapped[float | None] = mapped_column(Numeric(16, 2))
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    amount_low_eur: Mapped[float | None] = mapped_column(Numeric(16, 2))
    amount_central_eur: Mapped[float | None] = mapped_column(Numeric(16, 2))
    amount_high_eur: Mapped[float | None] = mapped_column(Numeric(16, 2))
    rate_to_eur: Mapped[float | None] = mapped_column(Numeric(24, 12))
    fx_rate_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    fx_source: Mapped[str | None] = mapped_column(Text)
    fx_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fx_rates.id")
    )

    rate_low: Mapped[float | None] = mapped_column(Numeric(18, 10))
    rate_central: Mapped[float | None] = mapped_column(Numeric(18, 10))
    rate_high: Mapped[float | None] = mapped_column(Numeric(18, 10))

    incurred_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    provenance: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False, unique=True
    )
    amount_source: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    amount_eur: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False)
    rate_to_eur: Mapped[float] = mapped_column(Numeric(24, 12), nullable=False)
    fx_rate_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    fx_source: Mapped[str] = mapped_column(Text, nullable=False)
    fx_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fx_rates.id")
    )
    purchased_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    payment_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'paid'")
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class SaleListing(Base):
    __tablename__ = "sale_listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    platform_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id")
    )
    asking_amount_source: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    asking_amount_eur: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False)
    rate_to_eur: Mapped[float] = mapped_column(Numeric(24, 12), nullable=False)
    fx_rate_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    fx_source: Mapped[str] = mapped_column(Text, nullable=False)
    fx_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fx_rates.id")
    )
    listed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    external_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        pg_enum(ListingStatus, "listing_status"),
        nullable=False,
        server_default=text("'active'"),
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False, unique=True
    )
    sale_listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sale_listings.id")
    )
    realized_amount_source: Mapped[float] = mapped_column(
        Numeric(16, 2), nullable=False
    )
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    realized_amount_eur: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False)
    rate_to_eur: Mapped[float] = mapped_column(Numeric(24, 12), nullable=False)
    fx_rate_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    fx_source: Mapped[str] = mapped_column(Text, nullable=False)
    fx_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fx_rates.id")
    )
    sold_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    payout_received_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    buyer_reference: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
