from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, ForeignKey, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class FxRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    base_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(
        CHAR(3), nullable=False, server_default=text("'EUR'")
    )
    rate: Mapped[float] = mapped_column(Numeric(24, 12), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "base_currency",
            "quote_currency",
            "observed_at",
            "source_name",
            name="fx_rates_base_currency_quote_currency_observed_at_source_na_key",
        ),
    )


class Ruleset(Base):
    __tablename__ = "rulesets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    version: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
