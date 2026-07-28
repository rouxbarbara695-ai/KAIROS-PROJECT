from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.shared.domain.redaction import redact
from app.shared.infrastructure.db.models.audit import AuditEvent


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    resource_type: str
    resource_id: uuid.UUID
    action: str
    reason: str
    actor_user_id: uuid.UUID | None
    before_data: dict[str, object] | None
    after_data: dict[str, object] | None
    occurred_at: datetime


class AuditEventPage(BaseModel):
    items: list[AuditEventResponse]
    next_cursor: str | None


def to_audit_event_response(event: AuditEvent) -> AuditEventResponse:
    """`before_data` et `after_data` sont du JSON libre : rien dans le schéma
    n'empêche une charge future d'y déposer une donnée sensible. La rédaction
    est appliquée à la sortie plutôt que supposée à l'entrée (règle 11)."""

    return AuditEventResponse(
        id=event.id,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        action=event.action,
        reason=event.reason,
        actor_user_id=event.actor_user_id,
        before_data=redact(event.before_data) if event.before_data else None,
        after_data=redact(event.after_data) if event.after_data else None,
        occurred_at=event.occurred_at,
    )
