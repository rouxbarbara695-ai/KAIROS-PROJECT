from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.events import (
    AuditEventPage,
    to_audit_event_response,
)
from app.api.v1.schemas.opportunities import (
    CreateOpportunityRequest,
    OpportunityPage,
    OpportunityPatchRequest,
    OpportunityResponse,
    PriceInputCreate,
    ReferenceConfirmationRequest,
    SellerProfilePatchRequest,
    WatchProfilePatchRequest,
)
from app.audit.application.list_events import list_opportunity_events
from app.identity.application.reference_confirmation import confirm_reference
from app.identity.application.seller_profile import patch_seller_profile
from app.identity.application.watch_profile import patch_watch_profile
from app.opportunities.application.add_price_input import add_price_input
from app.opportunities.application.create_opportunity import create_opportunity
from app.opportunities.application.get_opportunity import get_opportunity
from app.opportunities.application.list_opportunities import (
    OpportunityListFilters,
    list_opportunities,
)
from app.opportunities.application.patch_opportunity import patch_opportunity
from app.opportunities.application.presenters import to_opportunity_response
from app.shared.config import Settings, get_settings
from app.shared.domain.page import clamp_limit
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.platforms import Platform
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.principal_provider import get_current_principal

router = APIRouter(tags=["opportunities"])


async def _platform_code(session: AsyncSession, opportunity: Opportunity) -> str | None:
    """Code de la plateforme d'achat déclarée, s'il y en a une.

    Résolu ici plutôt que dans le présentateur : celui-ci reste une fonction
    pure, sans session ni requête.
    """

    if opportunity.purchase_platform_id is None:
        return None
    return (
        await session.execute(
            select(Platform.code).where(Platform.id == opportunity.purchase_platform_id)
        )
    ).scalar_one_or_none()


def _request_id(request: Request) -> uuid.UUID | None:
    raw = getattr(request.state, "request_id", None)
    try:
        return uuid.UUID(raw) if raw else None
    except ValueError:
        return None


@router.post(
    "/opportunities",
    status_code=status.HTTP_201_CREATED,
    response_model=OpportunityResponse,
)
async def create_opportunity_route(
    body: CreateOpportunityRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> OpportunityResponse:
    result = await create_opportunity(session, principal, body, settings)
    return to_opportunity_response(
        result.opportunity,
        result.watch,
        result.reference,
        result.seller,
        result.price_input,
        await _platform_code(session, result.opportunity),
    )


@router.get("/opportunities", response_model=OpportunityPage)
async def list_opportunities_route(
    status_filter: str | None = Query(default=None, alias="status"),
    brand: str | None = Query(default=None),
    reference: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> OpportunityPage:
    filters = OpportunityListFilters(
        status=status_filter, brand=brand, reference=reference
    )
    page = await list_opportunities(
        session, principal, filters, clamp_limit(limit), cursor
    )

    items = []
    for opportunity in page.items:
        _, watch, reference_row, seller, latest_price = await get_opportunity(
            session, principal, opportunity.id
        )
        items.append(
            to_opportunity_response(
                opportunity, watch, reference_row, seller, latest_price
            )
        )

    return OpportunityPage(items=items, next_cursor=page.next_cursor)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity_route(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> OpportunityResponse:
    opportunity, watch, reference, seller, latest_price = await get_opportunity(
        session, principal, opportunity_id
    )
    return to_opportunity_response(
        opportunity,
        watch,
        reference,
        seller,
        latest_price,
        await _platform_code(session, opportunity),
    )


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
async def patch_opportunity_route(
    opportunity_id: uuid.UUID,
    body: OpportunityPatchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> OpportunityResponse:
    await patch_opportunity(
        session, principal, opportunity_id, body, _request_id(request)
    )
    opportunity, watch, reference, seller, latest_price = await get_opportunity(
        session, principal, opportunity_id
    )
    return to_opportunity_response(
        opportunity,
        watch,
        reference,
        seller,
        latest_price,
        await _platform_code(session, opportunity),
    )


@router.post(
    "/opportunities/{opportunity_id}/reference-confirmations",
    response_model=OpportunityResponse,
)
async def confirm_reference_route(
    opportunity_id: uuid.UUID,
    body: ReferenceConfirmationRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> OpportunityResponse:
    await confirm_reference(
        session, principal, opportunity_id, body, _request_id(request)
    )
    opportunity, watch, reference, seller, latest_price = await get_opportunity(
        session, principal, opportunity_id
    )
    return to_opportunity_response(
        opportunity,
        watch,
        reference,
        seller,
        latest_price,
        await _platform_code(session, opportunity),
    )


@router.patch(
    "/opportunities/{opportunity_id}/watch-profile", response_model=OpportunityResponse
)
async def patch_watch_profile_route(
    opportunity_id: uuid.UUID,
    body: WatchProfilePatchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> OpportunityResponse:
    await patch_watch_profile(
        session, principal, opportunity_id, body, _request_id(request)
    )
    opportunity, watch, reference, seller, latest_price = await get_opportunity(
        session, principal, opportunity_id
    )
    return to_opportunity_response(
        opportunity,
        watch,
        reference,
        seller,
        latest_price,
        await _platform_code(session, opportunity),
    )


@router.patch(
    "/opportunities/{opportunity_id}/seller-profile", response_model=OpportunityResponse
)
async def patch_seller_profile_route(
    opportunity_id: uuid.UUID,
    body: SellerProfilePatchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> OpportunityResponse:
    await patch_seller_profile(
        session, principal, opportunity_id, body, _request_id(request)
    )
    opportunity, watch, reference, seller, latest_price = await get_opportunity(
        session, principal, opportunity_id
    )
    return to_opportunity_response(
        opportunity,
        watch,
        reference,
        seller,
        latest_price,
        await _platform_code(session, opportunity),
    )


@router.get("/opportunities/{opportunity_id}/events", response_model=AuditEventPage)
async def list_opportunity_events_route(
    opportunity_id: uuid.UUID,
    limit: int | None = Query(default=None),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> AuditEventPage:
    page = await list_opportunity_events(
        session, principal, opportunity_id, clamp_limit(limit), cursor
    )
    return AuditEventPage(
        items=[to_audit_event_response(event) for event in page.items],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/opportunities/{opportunity_id}/price-inputs", status_code=status.HTTP_201_CREATED
)
async def add_price_input_route(
    opportunity_id: uuid.UUID,
    body: PriceInputCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    price_input = await add_price_input(
        session, principal, opportunity_id, body, settings
    )
    return {"id": str(price_input.id)}
