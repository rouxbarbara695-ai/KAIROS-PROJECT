from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base
from app.shared.infrastructure.db.models.enums import JobStatus, pg_enum


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_method: Mapped[str] = mapped_column(Text, nullable=False)
    request_path: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "idempotency_key",
            name="idempotency_records_portfolio_id_idempotency_key_key",
        ),
    )


class CollectionJob(Base):
    __tablename__ = "collection_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id")
    )
    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platforms.id"), nullable=False
    )
    platform_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_rules.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        pg_enum(JobStatus, "job_status"),
        nullable=False,
        server_default=text("'queued'"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "idempotency_key",
            name="collection_jobs_portfolio_id_idempotency_key_key",
        ),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id")
    )
    opportunity_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunity_events.id")
    )
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    event_name: Mapped[str] = mapped_column(Text, nullable=False)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    allowed_properties: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
