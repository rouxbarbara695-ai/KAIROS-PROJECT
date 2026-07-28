from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.comparables import OverrideCreate
from app.audit.application.audit_log import record_audit_event
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.market import Comparable, ComparableOverride


async def current_override(
    session: AsyncSession, comparable_id: uuid.UUID
) -> ComparableOverride | None:
    """Dernier maillon de la chaîne d'overrides d'un comparable.

    La chaîne est append-only et `previous_override_id` est unique : le maillon
    courant est donc le seul qu'aucun autre ne désigne comme prédécesseur.
    """

    successor = select(ComparableOverride.previous_override_id).where(
        ComparableOverride.comparable_id == comparable_id,
        ComparableOverride.previous_override_id.is_not(None),
    )

    return (
        await session.execute(
            select(ComparableOverride).where(
                ComparableOverride.comparable_id == comparable_id,
                ComparableOverride.id.not_in(successor),
            )
        )
    ).scalar_one_or_none()


async def apply_override(
    session: AsyncSession,
    principal: Principal,
    comparable_id: uuid.UUID,
    request: OverrideCreate,
    request_id: uuid.UUID | None,
) -> ComparableOverride:
    """Corrige, exclut ou réintègre un comparable.

    Rien n'est jamais modifié ni supprimé : chaque décision ajoute un maillon
    qui référence le précédent, de sorte que l'historique complet des
    exclusions et réintégrations reste lisible (calculation-spec.md § 2).
    """

    comparable = (
        await session.execute(
            select(Comparable).where(
                Comparable.id == comparable_id,
                Comparable.portfolio_id.in_(principal.portfolio_ids),
            )
        )
    ).scalar_one_or_none()
    if comparable is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Comparable introuvable.")

    previous = await current_override(session, comparable_id)

    override = ComparableOverride(
        portfolio_id=comparable.portfolio_id,
        comparable_id=comparable.id,
        previous_override_id=previous.id if previous else None,
        excluded=request.excluded,
        exclusion_reason=request.exclusion_reason,
        corrected_data=request.corrected_data,
        actor_user_id=principal.user_id,
        reason=request.reason,
    )
    session.add(override)
    await session.flush()

    await record_audit_event(
        session,
        portfolio_id=comparable.portfolio_id,
        actor_user_id=principal.user_id,
        resource_type="comparable",
        resource_id=comparable.id,
        action="exclude" if request.excluded else "reinstate",
        reason=request.reason,
        before_data={
            "excluded": previous.excluded if previous else False,
            "corrected_data": dict(previous.corrected_data) if previous else {},
        },
        after_data={
            "excluded": request.excluded,
            "exclusion_reason": request.exclusion_reason,
            "corrected_data": request.corrected_data,
        },
        request_id=request_id,
    )

    await session.commit()
    await session.refresh(override)
    return override
