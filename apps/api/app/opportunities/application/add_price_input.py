from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.opportunities import PriceInputCreate
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.opportunities import (
    Opportunity,
    OpportunityPriceInput,
)
from app.shared.infrastructure.fx import resolve_fx


async def add_price_input(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    request: PriceInputCreate,
    settings: Settings,
) -> OpportunityPriceInput:
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

    if request.amount is None:
        price_input = OpportunityPriceInput(
            portfolio_id=opportunity.portfolio_id,
            opportunity_id=opportunity.id,
            kind=request.kind,
            missing_reason=request.missing_reason,
            actor_user_id=principal.user_id,
        )
    else:
        assert request.currency is not None
        fx = await resolve_fx(session, request.currency, settings.fx_max_age_hours)
        if fx is None:
            raise DomainError(
                ErrorCode.FX_RATE_UNAVAILABLE,
                f"Aucun taux de change récent pour {request.currency}.",
            )
        price_input = OpportunityPriceInput(
            portfolio_id=opportunity.portfolio_id,
            opportunity_id=opportunity.id,
            kind=request.kind,
            amount_source=request.amount,
            currency=request.currency.upper(),
            amount_eur=fx.convert(request.amount),
            rate_to_eur=fx.rate_to_eur,
            fx_rate_at=fx.fx_rate_at,
            fx_source=fx.fx_source,
            fx_rate_id=fx.fx_rate_id,
            actor_user_id=principal.user_id,
        )

    session.add(price_input)
    await session.commit()
    return price_input
