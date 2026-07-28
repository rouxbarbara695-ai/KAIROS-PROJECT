from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base
from app.shared.infrastructure.db.models.enums import (
    AnalysisState,
    Recommendation,
    pg_enum,
)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    valuation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market_valuations.id")
    )
    previous_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id"), unique=True
    )
    ruleset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rulesets.id"), nullable=False
    )
    strategy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_versions.id")
    )
    platform_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_rules.id")
    )
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        pg_enum(AnalysisState, "analysis_state"),
        nullable=False,
        server_default=text("'draft'"),
    )
    calculated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    current_price_eur: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    total_cost_eur: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    expected_sale_price_eur: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    raw_max_purchase_price_eur: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    max_purchase_price_eur: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    expected_profit_eur: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    expected_roi: Mapped[Decimal | None] = mapped_column(Numeric(18, 10))
    expected_days_to_sell: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    evidence_quality_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    recommendation: Mapped[str] = mapped_column(
        pg_enum(Recommendation, "recommendation"), nullable=False
    )

    gates: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    pillars: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    scenario_results: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    caps: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    explanation: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ruleset_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    strategy_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    platform_rule_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    portfolio_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
