from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    before_data: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    after_data: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
