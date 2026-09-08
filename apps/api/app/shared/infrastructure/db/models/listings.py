from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import (
    Base,
    portfolio_identity_index,
    same_portfolio_fk,
)
from app.shared.infrastructure.db.models.enums import ListingStatus, PriceKind, pg_enum


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id"), nullable=False
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id")
    )
    watch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watches.id"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        pg_enum(ListingStatus, "listing_status"),
        nullable=False,
        server_default=text("'unknown'"),
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    last_success_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        # Index unique et non `UniqueConstraint` : c'est un index en base, et
        # les deux ne sont pas interchangeables pour la comparaison de schéma.
        Index(
            "listings_canonical_url_uq", "portfolio_id", "canonical_url", unique=True
        ),
        # Partiel : deux annonces sans identifiant externe doivent pouvoir
        # coexister. C'est le cas dès qu'une plateforme n'en expose pas.
        Index(
            "listings_external_id_uq",
            "portfolio_id",
            "platform_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id is not null"),
        ),
        portfolio_identity_index("listings"),
        Index(
            "listings_portfolio_watch_identity_uq",
            "portfolio_id",
            "id",
            "watch_id",
            unique=True,
        ),
        same_portfolio_fk("seller_id", "sellers", "listings_seller_same_portfolio_fk"),
    )


class ListingObservation(Base):
    __tablename__ = "listing_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id"), nullable=False
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    observed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        pg_enum(ListingStatus, "listing_status"), nullable=False
    )
    reserve_met: Mapped[bool | None] = mapped_column(Boolean)
    auction_end_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    condition_data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    completeness_data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    raw_data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    fetch_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'success'")
    )
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "collection_id",
            name="listing_observations_listing_id_collection_id_key",
        ),
        Index(
            "listing_observations_latest_idx",
            "portfolio_id",
            "listing_id",
            text("observed_at desc"),
            text("id desc"),
        ),
        portfolio_identity_index("listing_observations"),
        same_portfolio_fk(
            "listing_id", "listings", "observations_listing_same_portfolio_fk"
        ),
    )


class ListingObservationPrice(Base):
    __tablename__ = "listing_observation_prices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listing_observations.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(pg_enum(PriceKind, "price_kind"), nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "observation_id",
            "kind",
            name="listing_observation_prices_observation_id_kind_key",
        ),
        same_portfolio_fk(
            "observation_id",
            "listing_observations",
            "observation_prices_same_portfolio_fk",
        ),
    )
