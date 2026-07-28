from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INTERVAL, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base
from app.shared.infrastructure.db.models.enums import PlatformAccessMethod, pg_enum


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class PlatformRule(Base):
    __tablename__ = "platform_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id"), nullable=False
    )
    region_code: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'*'")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    access_method: Mapped[str] = mapped_column(
        pg_enum(PlatformAccessMethod, "platform_access_method"),
        nullable=False,
        server_default=text("'manual'"),
    )
    access_authorized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    min_poll_interval: Mapped[timedelta | None] = mapped_column(INTERVAL)
    max_poll_interval: Mapped[timedelta | None] = mapped_column(INTERVAL)

    buyer_fee_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 10))
    buyer_fee_fixed: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    buyer_fee_currency: Mapped[str | None] = mapped_column(CHAR(3))
    buyer_fee_basis: Mapped[str | None] = mapped_column(Text)
    buyer_fee_min: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    buyer_fee_max: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))

    seller_fee_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 10))
    seller_fee_fixed: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    seller_fee_currency: Mapped[str | None] = mapped_column(CHAR(3))
    seller_fee_basis: Mapped[str | None] = mapped_column(Text)
    seller_fee_min: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    seller_fee_max: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))

    payment_rules: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    shipping_rules: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    protection_rules: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    tax_rules: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    can_observe_active_listing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    can_observe_auction_result: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    can_observe_realized_sale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    provenance_url: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "platform_id",
            "region_code",
            "version",
            name="platform_rules_platform_id_region_code_version_key",
        ),
    )
