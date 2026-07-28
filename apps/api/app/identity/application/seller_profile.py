from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.opportunities import SellerProfilePatchRequest
from app.audit.application.audit_log import record_audit_event
from app.identity.domain import vocabularies as vocab
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.watches import Seller


async def patch_seller_profile(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    request: SellerProfilePatchRequest,
    request_id: uuid.UUID | None,
) -> Seller:
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

    seller = None
    if opportunity.seller_id is not None:
        seller = (
            await session.execute(
                select(Seller).where(Seller.id == opportunity.seller_id)
            )
        ).scalar_one_or_none()

    if seller is None:
        seller = Seller(portfolio_id=opportunity.portfolio_id)
        session.add(seller)
        await session.flush()
        opportunity.seller_id = seller.id
        before: dict[str, object] = {"country_code": None, "seller_type": None}
    else:
        before = {
            "country_code": seller.country_code,
            "seller_type": seller.seller_type,
        }

    if request.country_code is not None:
        seller.country_code = request.country_code.upper()
    if request.seller_type is not None:
        seller.seller_type = vocab.normalize(
            request.seller_type, vocab.SELLER_TYPES, vocab.SELLER_TYPE_FALLBACK
        )

    after = {"country_code": seller.country_code, "seller_type": seller.seller_type}

    await record_audit_event(
        session,
        portfolio_id=opportunity.portfolio_id,
        actor_user_id=principal.user_id,
        resource_type="seller",
        resource_id=seller.id,
        action="correct",
        reason=request.reason,
        before_data=before,
        after_data=after,
        request_id=request_id,
    )

    await session.commit()
    return seller
