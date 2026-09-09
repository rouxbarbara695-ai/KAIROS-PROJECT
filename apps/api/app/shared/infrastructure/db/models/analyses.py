from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import (
    Base,
    portfolio_identity_index,
    same_portfolio_fk,
)
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
    # Pas de `unique=True` ici : cela produirait une contrainte d'unicité
    # anonyme et **totale**, là où la base porte un index unique **partiel**
    # (`where previous_analysis_id is not null`). Sans le `where`, deux
    # analyses initiales — dont le prédécesseur est nul — entreraient en
    # collision. L'index est déclaré dans `__table_args__`.
    previous_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id")
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

    __table_args__ = (
        Index(
            "analyses_opportunity_date_idx",
            "portfolio_id",
            "opportunity_id",
            text("calculated_at desc"),
            text("id desc"),
        ),
        portfolio_identity_index("analyses"),
        # Une analyse ne peut avoir qu'un seul successeur : le chaînage doit
        # rester une ligne, pas un arbre. Deux recalculs partant de la même
        # analyse rendraient l'historique impossible à lire dans l'ordre.
        Index(
            "analyses_previous_child_uq",
            "previous_analysis_id",
            unique=True,
            postgresql_where=text("previous_analysis_id is not null"),
        ),
        same_portfolio_fk(
            "opportunity_id", "opportunities", "analyses_opportunity_same_portfolio_fk"
        ),
        same_portfolio_fk(
            "strategy_version_id",
            "strategy_versions",
            "analyses_strategy_version_same_portfolio_fk",
        ),
        same_portfolio_fk(
            "valuation_id", "market_valuations", "analyses_valuation_same_portfolio_fk"
        ),
    )
