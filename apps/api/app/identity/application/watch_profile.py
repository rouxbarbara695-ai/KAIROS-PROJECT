from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.opportunities import WatchProfilePatchRequest
from app.audit.application.audit_log import record_audit_event
from app.identity.domain import vocabularies as vocab
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.watches import Watch


async def patch_watch_profile(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    request: WatchProfilePatchRequest,
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
        "condition_data": dict(watch.condition_data),
        "completeness_data": dict(watch.completeness_data),
        "raw_input": dict(watch.raw_input),
    }

    raw_input = dict(watch.raw_input)
    if request.mechanical_condition is not None:
        raw_input["mechanical_condition"] = request.mechanical_condition
    if request.cosmetic_condition is not None:
        raw_input["cosmetic_condition"] = request.cosmetic_condition
    if request.originality is not None:
        raw_input["originality"] = request.originality
    if request.box is not None:
        raw_input["box"] = request.box
    if request.papers is not None:
        raw_input["papers"] = request.papers

    condition_data = dict(watch.condition_data)
    if request.mechanical_condition is not None:
        condition_data["mechanical"] = vocab.normalize(
            request.mechanical_condition,
            vocab.MECHANICAL_CONDITIONS,
            vocab.MECHANICAL_FALLBACK,
        )
    if request.cosmetic_condition is not None:
        condition_data["cosmetic"] = vocab.normalize(
            request.cosmetic_condition,
            vocab.COSMETIC_CONDITIONS,
            vocab.COSMETIC_FALLBACK,
        )
    if request.originality is not None:
        condition_data["originality"] = vocab.normalize(
            request.originality, vocab.ORIGINALITY_LEVELS, vocab.ORIGINALITY_FALLBACK
        )

    completeness_data = dict(watch.completeness_data)
    if request.box is not None or request.papers is not None:
        stored_box = raw_input.get("box")
        stored_papers = raw_input.get("papers")
        completeness_data["level"] = vocab.completeness_level(
            request.box
            if request.box is not None
            else (stored_box if isinstance(stored_box, bool) else None),
            request.papers
            if request.papers is not None
            else (stored_papers if isinstance(stored_papers, bool) else None),
        )

    watch.raw_input = raw_input
    watch.condition_data = condition_data
    watch.completeness_data = completeness_data

    after = {
        "condition_data": condition_data,
        "completeness_data": completeness_data,
        "raw_input": raw_input,
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
