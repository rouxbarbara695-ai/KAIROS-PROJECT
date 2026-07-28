from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.db.models.audit import AuditEvent


async def record_audit_event(
    session: AsyncSession,
    *,
    portfolio_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    resource_type: str,
    resource_id: uuid.UUID,
    action: str,
    reason: str,
    before_data: dict[str, Any] | None,
    after_data: dict[str, Any] | None,
    request_id: uuid.UUID | None,
) -> None:
    """Écrit une ligne d'audit append-only (KAI-103). `after_data` est
    obligatoire pour correct/exclude/reinstate — contrainte déjà imposée par
    la base, revérifiée ici pour échouer tôt côté application."""

    if action in ("correct", "exclude", "reinstate") and after_data is None:
        raise ValueError(f"after_data est obligatoire pour l'action '{action}'.")

    session.add(
        AuditEvent(
            portfolio_id=portfolio_id,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            reason=reason,
            before_data=before_data,
            after_data=after_data,
            request_id=request_id,
        )
    )
