from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import (
    Base,
    portfolio_identity_index,
    same_portfolio_fk,
)
from app.shared.infrastructure.db.models.enums import (
    OpportunitySourceMode,
    OpportunityStatus,
    PriceKind,
    ReferenceConfirmationStatus,
    pg_enum,
)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    source_mode: Mapped[str] = mapped_column(
        pg_enum(OpportunitySourceMode, "opportunity_source_mode"), nullable=False
    )
    manual_identifier: Mapped[str | None] = mapped_column(Text)
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id")
    )
    watch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watches.id"), nullable=False
    )
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id")
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategies.id")
    )
    purchase_platform_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id")
    )
    status: Mapped[str] = mapped_column(
        pg_enum(OpportunityStatus, "opportunity_status"),
        nullable=False,
        server_default=text("'watching'"),
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        # Index **partiels**, et c'est la seule forme correcte. Une
        # `UniqueConstraint` ordinaire traiterait tous les `null` comme
        # distincts en PostgreSQL — l'unicité tiendrait par accident. Surtout,
        # elle empêcherait deux opportunités sans identifiant manuel de
        # coexister sur d'autres bases. Le `where ... is not null` dit ce qu'on
        # veut vraiment : ces colonnes sont uniques *quand elles sont
        # renseignées*.
        Index(
            "opportunities_manual_identifier_uq",
            "portfolio_id",
            "manual_identifier",
            unique=True,
            postgresql_where=text("manual_identifier is not null"),
        ),
        Index(
            "opportunities_listing_uq",
            "portfolio_id",
            "listing_id",
            unique=True,
            postgresql_where=text("listing_id is not null"),
        ),
        portfolio_identity_index("opportunities"),
        # `(portfolio_id, id, watch_id)` : cible de la clé qui interdit qu'une
        # confirmation de référence porte sur une autre montre que celle de
        # l'opportunité.
        Index(
            "opportunities_portfolio_watch_identity_uq",
            "portfolio_id",
            "id",
            "watch_id",
            unique=True,
        ),
        same_portfolio_fk(
            "listing_id", "listings", "opportunities_listing_same_portfolio_fk"
        ),
        same_portfolio_fk(
            "seller_id", "sellers", "opportunities_seller_same_portfolio_fk"
        ),
        same_portfolio_fk(
            "strategy_id", "strategies", "opportunities_strategy_same_portfolio_fk"
        ),
        # Trois colonnes : l'annonce rattachée doit porter la même montre que
        # l'opportunité. Sans cela, une correction de montre d'un côté
        # laisserait les deux en désaccord sans que rien ne le signale.
        ForeignKeyConstraint(
            ["portfolio_id", "listing_id", "watch_id"],
            ["listings.portfolio_id", "listings.id", "listings.watch_id"],
            name="opportunities_listing_watch_match_fk",
        ),
    )

    # Verrou optimiste. Chaque `UPDATE` émis par l'ORM porte désormais
    # `where version = <valeur lue>` : si une autre transaction a écrit
    # entre-temps, aucune ligne ne correspond et SQLAlchemy lève
    # `StaleDataError`, traduite en `RESOURCE_VERSION_CONFLICT`.
    #
    # C'est la condition `where` qui fait la garantie, pas une comparaison
    # préalable en Python : entre une lecture et une écriture séparées, une
    # écriture concurrente passe. Ici, PostgreSQL réévalue la condition sur la
    # ligne réellement verrouillée.
    #
    # `version_id_generator=False` parce que le déclencheur `opportunities_touch`
    # incrémente déjà `version` en base : le générateur de SQLAlchemy et le
    # déclencheur se disputeraient la valeur. Chaque écriture doit donc poser
    # `opportunity.version += 1` — ce que le déclencheur recalcule à
    # l'identique.
    __mapper_args__ = {
        "version_id_col": version,
        "version_id_generator": False,
    }


class OpportunityPriceInput(Base):
    __tablename__ = "opportunity_price_inputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(pg_enum(PriceKind, "price_kind"), nullable=False)
    amount_source: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    amount_eur: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    rate_to_eur: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    fx_rate_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    fx_source: Mapped[str | None] = mapped_column(Text)
    fx_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fx_rates.id")
    )
    missing_reason: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        # Le dernier prix d'un type donné se lit sans parcourir tout
        # l'historique : `observed_at DESC, id DESC` fait de la lecture la plus
        # fréquente un accès direct.
        Index(
            "opportunity_price_inputs_latest_idx",
            "portfolio_id",
            "opportunity_id",
            "kind",
            text("observed_at desc"),
            text("id desc"),
        ),
        same_portfolio_fk(
            "opportunity_id",
            "opportunities",
            "price_inputs_opportunity_same_portfolio_fk",
        ),
    )


class ReferenceConfirmation(Base):
    __tablename__ = "reference_confirmations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    watch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watches.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        pg_enum(ReferenceConfirmationStatus, "reference_confirmation_status"),
        nullable=False,
    )
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watch_references.id")
    )
    identification_confidence: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        same_portfolio_fk(
            "opportunity_id",
            "opportunities",
            "confirmations_opportunity_same_portfolio_fk",
        ),
        # La confirmation porte sur la montre de son opportunité, pas sur une
        # autre : une référence confirmée sur la mauvaise montre serait une
        # preuve fausse, et les preuves sont immuables.
        ForeignKeyConstraint(
            ["portfolio_id", "opportunity_id", "watch_id"],
            [
                "opportunities.portfolio_id",
                "opportunities.id",
                "opportunities.watch_id",
            ],
            name="confirmations_opportunity_watch_match_fk",
        ),
    )


class OpportunityEvent(Base):
    __tablename__ = "opportunity_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str | None] = mapped_column(
        pg_enum(OpportunityStatus, "opportunity_status")
    )
    to_status: Mapped[str | None] = mapped_column(
        pg_enum(OpportunityStatus, "opportunity_status")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index(
            "opportunity_events_date_idx",
            "portfolio_id",
            "opportunity_id",
            text("occurred_at desc"),
            text("id desc"),
        ),
        portfolio_identity_index("opportunity_events"),
        same_portfolio_fk(
            "opportunity_id", "opportunities", "events_opportunity_same_portfolio_fk"
        ),
    )
