from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.opportunities import OpportunityPatchRequest
from app.audit.application.audit_log import record_audit_event
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.strategies import Strategy


async def patch_opportunity(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    request: OpportunityPatchRequest,
    request_id: uuid.UUID | None,
) -> Opportunity:
    """Liste blanche stricte (KAI-103) : seule la stratégie sélectionnée est
    corrigible ici. Référence, état, set, vendeur, prix et données
    financières passent par leurs commandes dédiées."""

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

    if request.strategy_id is not None:
        strategy = (
            await session.execute(
                select(Strategy).where(
                    Strategy.id == request.strategy_id,
                    Strategy.portfolio_id == opportunity.portfolio_id,
                )
            )
        ).scalar_one_or_none()
        if strategy is None:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                "Stratégie introuvable dans ce portefeuille.",
                field="strategy_id",
            )

    before = {
        "strategy_id": str(opportunity.strategy_id) if opportunity.strategy_id else None
    }
    opportunity.strategy_id = request.strategy_id
    after = {
        "strategy_id": str(opportunity.strategy_id) if opportunity.strategy_id else None
    }

    await record_audit_event(
        session,
        portfolio_id=opportunity.portfolio_id,
        actor_user_id=principal.user_id,
        resource_type="opportunity",
        resource_id=opportunity.id,
        action="correct",
        reason=request.reason,
        before_data=before,
        after_data=after,
        request_id=request_id,
    )

    await session.commit()
    return opportunity
