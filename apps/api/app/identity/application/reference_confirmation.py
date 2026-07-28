from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.opportunities import ReferenceConfirmationRequest
from app.audit.application.audit_log import record_audit_event
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.opportunities import (
    Opportunity,
    ReferenceConfirmation,
)
from app.shared.infrastructure.db.models.watches import Watch


async def confirm_reference(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    request: ReferenceConfirmationRequest,
    request_id: uuid.UUID | None,
) -> Watch:
    opportunity = (
        await session.execute(
            select(Opportunity).where(
                Opportunity.id == opportunity_id,
                Opportunity.portfolio_id.in_(principal.portfolio_ids),
            )
        )
    ).scalar_one_or_none()
    if opportunity is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Opportunité introuvable.")

    watch = (
        await session.execute(select(Watch).where(Watch.id == opportunity.watch_id))
    ).scalar_one()

    before = {
        "reference_status": watch.reference_status,
        "reference_id": str(watch.reference_id) if watch.reference_id else None,
    }

    session.add(
        ReferenceConfirmation(
            portfolio_id=opportunity.portfolio_id,
            opportunity_id=opportunity.id,
            watch_id=watch.id,
            status=request.status,
            reference_id=request.reference_id,
            actor_user_id=principal.user_id,
            reason=request.reason,
        )
    )

    watch.reference_status = request.status
    if request.status in ("confirmed", "corrected"):
        watch.reference_id = request.reference_id
        watch.reference_confirmed_by_user_id = principal.user_id
        watch.reference_confirmed_at = datetime.now(UTC)

    after = {
        "reference_status": watch.reference_status,
        "reference_id": str(watch.reference_id) if watch.reference_id else None,
    }

    await record_audit_event(
        session,
        portfolio_id=opportunity.portfolio_id,
        actor_user_id=principal.user_id,
        resource_type="watch",
        resource_id=watch.id,
        action="correct",
        reason=request.reason,
        before_data=before,
        after_data=after,
        request_id=request_id,
    )

    await session.commit()
    return watch
