from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.opportunities import (
    Opportunity,
    OpportunityPriceInput,
)
from app.shared.infrastructure.db.models.watches import Seller, Watch, WatchReference


async def get_opportunity(
    session: AsyncSession, principal: Principal, opportunity_id: uuid.UUID
) -> tuple[
    Opportunity,
    Watch,
    WatchReference | None,
    Seller | None,
    OpportunityPriceInput | None,
]:
    """Filtre systématiquement par les portefeuilles du principal : une
    opportunité d'un autre portefeuille est indiscernable d'une opportunité
    inexistante (404, jamais 403 — pas de fuite d'existence)."""

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

    reference = None
    if watch.reference_id is not None:
        reference = (
            await session.execute(
                select(WatchReference).where(WatchReference.id == watch.reference_id)
            )
        ).scalar_one_or_none()

    seller = None
    if opportunity.seller_id is not None:
        seller = (
            await session.execute(
                select(Seller).where(Seller.id == opportunity.seller_id)
            )
        ).scalar_one_or_none()

    latest_price = (
        await session.execute(
            select(OpportunityPriceInput)
            .where(OpportunityPriceInput.opportunity_id == opportunity.id)
            .order_by(
                OpportunityPriceInput.observed_at.desc(),
                OpportunityPriceInput.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    return opportunity, watch, reference, seller, latest_price
