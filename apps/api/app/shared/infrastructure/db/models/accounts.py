from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_currency: Mapped[str] = mapped_column(
        CHAR(3), nullable=False, server_default=text("'EUR'")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class PortfolioMember(Base):
    __tablename__ = "portfolio_members"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolios.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
