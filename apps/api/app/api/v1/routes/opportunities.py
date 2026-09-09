from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.idempotency import Idempotency, IdempotencyKey, get_idempotency
from app.api.v1.preconditions import IfMatch, required_version, tag
from app.api.v1.schemas.common import DecimalString
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
from app.operations.application.change_status import change_status
from app.operations.application.record_purchase import record_purchase
from app.operations.application.sell import (
    record_payout,
    record_sale,
    record_sale_listing,
)
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
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.page import clamp_limit
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.platforms import Platform
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.portfolio_lookup import portfolio_of_opportunity
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


async def _present(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    response: Response,
) -> OpportunityResponse:
    """Relit le dossier et l'étiquette de sa version.

    Toutes les réponses qui portent une opportunité passent par ici : l'`ETag`
    doit accompagner **chaque** lecture, sinon le client n'a pas de version à
    renvoyer dans `If-Match` après la première correction.
    """

    opportunity, watch, reference, seller, latest_price = await get_opportunity(
        session, principal, opportunity_id
    )
    tag(response, opportunity.version)
    return to_opportunity_response(
        opportunity,
        watch,
        reference,
        seller,
        latest_price,
        await _platform_code(session, opportunity),
    )


@router.post(
    "/opportunities",
    status_code=status.HTTP_201_CREATED,
    response_model=OpportunityResponse,
)
async def create_opportunity_route(
    body: CreateOpportunityRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
    idempotency: Idempotency = Depends(get_idempotency),
    idempotency_key: IdempotencyKey = None,
) -> OpportunityResponse:
    # Le portefeuille vient du corps : à la création, aucune ressource
    # existante ne peut le fournir. Le contrôle est répété ici, avant la
    # réservation, pour qu'une clé ne soit jamais consommée sur un
    # portefeuille étranger. Même code que le cas d'usage, sinon la réponse
    # changerait selon que l'appel porte une clé ou non.
    if not principal.owns_portfolio(body.portfolio_id):
        raise DomainError(
            ErrorCode.FORBIDDEN, "Ce portefeuille n'appartient pas au principal."
        )

    async with idempotency.guard(
        request, body.portfolio_id, OpportunityResponse, idempotency_key
    ) as place:
        if place.replay is not None:
            return place.replay

        result = await create_opportunity(session, principal, body, settings)
        tag(response, result.opportunity.version)
        return place.completed(
            to_opportunity_response(
                result.opportunity,
                result.watch,
                result.reference,
                result.seller,
                result.price_input,
                await _platform_code(session, result.opportunity),
            )
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
    response: Response,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> OpportunityResponse:
    return await _present(session, principal, opportunity_id, response)


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
async def patch_opportunity_route(
    opportunity_id: uuid.UUID,
    body: OpportunityPatchRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    if_match: IfMatch = None,
) -> OpportunityResponse:
    await patch_opportunity(
        session,
        principal,
        opportunity_id,
        body,
        _request_id(request),
        required_version(if_match),
    )
    return await _present(session, principal, opportunity_id, response)


@router.post(
    "/opportunities/{opportunity_id}/reference-confirmations",
    response_model=OpportunityResponse,
)
async def confirm_reference_route(
    opportunity_id: uuid.UUID,
    body: ReferenceConfirmationRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> OpportunityResponse:
    await confirm_reference(
        session, principal, opportunity_id, body, _request_id(request)
    )
    return await _present(session, principal, opportunity_id, response)


@router.patch(
    "/opportunities/{opportunity_id}/watch-profile", response_model=OpportunityResponse
)
async def patch_watch_profile_route(
    opportunity_id: uuid.UUID,
    body: WatchProfilePatchRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    if_match: IfMatch = None,
) -> OpportunityResponse:
    await patch_watch_profile(
        session,
        principal,
        opportunity_id,
        body,
        _request_id(request),
        required_version(if_match),
    )
    return await _present(session, principal, opportunity_id, response)


@router.patch(
    "/opportunities/{opportunity_id}/seller-profile", response_model=OpportunityResponse
)
async def patch_seller_profile_route(
    opportunity_id: uuid.UUID,
    body: SellerProfilePatchRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    if_match: IfMatch = None,
) -> OpportunityResponse:
    await patch_seller_profile(
        session,
        principal,
        opportunity_id,
        body,
        _request_id(request),
        required_version(if_match),
    )
    return await _present(session, principal, opportunity_id, response)


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


class PurchaseCreate(BaseModel):
    """Achat effectivement conclu.

    `amount` est ce qui a **réellement** été payé. L'écran ne le préremplit ni
    avec le prix affiché ni avec le maximum calculé : reprendre l'un des deux
    ferait de KAIROS un outil qui se relit lui-même, et le coût de revient
    serait faux dès la première négociation réussie.
    """

    amount: DecimalString
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    purchased_at: datetime | None = None
    reason: str = Field(min_length=1)


class StatusChangeRequest(BaseModel):
    status: str
    reason: str = Field(min_length=1)


@router.post(
    "/opportunities/{opportunity_id}/purchase",
    status_code=status.HTTP_201_CREATED,
)
async def record_purchase_route(
    opportunity_id: uuid.UUID,
    body: PurchaseCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
    idempotency: Idempotency = Depends(get_idempotency),
    idempotency_key: IdempotencyKey = None,
) -> dict[str, str]:
    """Enregistre l'achat : ligne d'achat, sortie de trésorerie et passage en
    `purchased`, dans une seule transaction."""

    portfolio_id = await portfolio_of_opportunity(session, principal, opportunity_id)
    async with idempotency.guard(request, portfolio_id, dict, idempotency_key) as place:
        if place.replay is not None:
            return place.replay

        purchase = await record_purchase(
            session,
            principal,
            opportunity_id,
            amount=body.amount,
            currency=body.currency,
            purchased_at=body.purchased_at,
            reason=body.reason,
            settings=settings,
        )
        return place.completed(
            {
                "id": str(purchase.id),
                "amount_eur": str(purchase.amount_eur),
                "purchased_at": purchase.purchased_at.isoformat(),
            }
        )


@router.post(
    "/opportunities/{opportunity_id}/status", response_model=OpportunityResponse
)
async def change_status_route(
    opportunity_id: uuid.UUID,
    body: StatusChangeRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    idempotency: Idempotency = Depends(get_idempotency),
    idempotency_key: IdempotencyKey = None,
) -> OpportunityResponse:
    """Change le statut, avec motif. Les statuts qui constatent une opération
    — `purchased`, `sold` — s'obtiennent en enregistrant l'opération."""

    portfolio_id = await portfolio_of_opportunity(session, principal, opportunity_id)
    async with idempotency.guard(
        request, portfolio_id, OpportunityResponse, idempotency_key
    ) as place:
        if place.replay is not None:
            return place.replay

        await change_status(
            session, principal, opportunity_id, target=body.status, reason=body.reason
        )
        return place.completed(
            await _present(session, principal, opportunity_id, response)
        )


class SaleListingCreate(BaseModel):
    """Mise en vente : canal et prix demandé.

    `asking_amount` n'est pas le prix d'affichage recommandé par l'analyse. On
    peut viser plus haut pour garder de la marge de négociation, ou plus bas
    pour partir vite : c'est une décision commerciale, et l'enregistrer telle
    quelle est la seule façon d'en mesurer la justesse après coup.
    """

    asking_amount: DecimalString
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    platform_code: str | None = None
    external_url: str | None = None
    listed_at: datetime | None = None
    reason: str = Field(min_length=1)


class SaleCreate(BaseModel):
    """Vente conclue : la montre part, les fonds sont encore retenus."""

    realized_amount: DecimalString
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    sold_at: datetime | None = None
    reason: str = Field(min_length=1)


class PayoutCreate(BaseModel):
    """Encaissement constaté.

    `amount` est ce qui est **réellement arrivé sur le compte**, commission de
    plateforme déjà déduite. Laissé vide, le prix réalisé fait foi — ce qui
    correspond à une vente sans intermédiaire.
    """

    amount: DecimalString | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    received_at: datetime | None = None
    reason: str = Field(min_length=1)


@router.post(
    "/opportunities/{opportunity_id}/sale-listing",
    status_code=status.HTTP_201_CREATED,
)
async def record_sale_listing_route(
    opportunity_id: uuid.UUID,
    body: SaleListingCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
    idempotency: Idempotency = Depends(get_idempotency),
    idempotency_key: IdempotencyKey = None,
) -> dict[str, str | None]:
    portfolio_id = await portfolio_of_opportunity(session, principal, opportunity_id)
    async with idempotency.guard(request, portfolio_id, dict, idempotency_key) as place:
        if place.replay is not None:
            return place.replay

        listing = await record_sale_listing(
            session,
            principal,
            opportunity_id,
            asking_amount=body.asking_amount,
            currency=body.currency,
            platform_code=body.platform_code,
            external_url=body.external_url,
            listed_at=body.listed_at,
            reason=body.reason,
            settings=settings,
        )
        return place.completed(
            {
                "id": str(listing.id),
                "asking_amount_eur": str(listing.asking_amount_eur),
                "listed_at": listing.listed_at.isoformat(),
            }
        )


@router.post(
    "/opportunities/{opportunity_id}/sale", status_code=status.HTTP_201_CREATED
)
async def record_sale_route(
    opportunity_id: uuid.UUID,
    body: SaleCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
    idempotency: Idempotency = Depends(get_idempotency),
    idempotency_key: IdempotencyKey = None,
) -> dict[str, str]:
    """Enregistre la vente. Aucune écriture de trésorerie : les fonds sont
    retenus jusqu'à l'encaissement."""

    portfolio_id = await portfolio_of_opportunity(session, principal, opportunity_id)
    async with idempotency.guard(request, portfolio_id, dict, idempotency_key) as place:
        if place.replay is not None:
            return place.replay

        sale = await record_sale(
            session,
            principal,
            opportunity_id,
            realized_amount=body.realized_amount,
            currency=body.currency,
            sold_at=body.sold_at,
            reason=body.reason,
            settings=settings,
        )
        return place.completed(
            {
                "id": str(sale.id),
                "realized_amount_eur": str(sale.realized_amount_eur),
                "sold_at": sale.sold_at.isoformat(),
            }
        )


@router.post("/opportunities/{opportunity_id}/payout")
async def record_payout_route(
    opportunity_id: uuid.UUID,
    body: PayoutCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
    idempotency: Idempotency = Depends(get_idempotency),
    idempotency_key: IdempotencyKey = None,
) -> dict[str, str | None]:
    """Constate l'encaissement : c'est ici que la trésorerie monte."""

    portfolio_id = await portfolio_of_opportunity(session, principal, opportunity_id)
    async with idempotency.guard(request, portfolio_id, dict, idempotency_key) as place:
        if place.replay is not None:
            return place.replay

        sale = await record_payout(
            session,
            principal,
            opportunity_id,
            amount=body.amount,
            currency=body.currency,
            received_at=body.received_at,
            reason=body.reason,
            settings=settings,
        )
        return place.completed(
            {
                "id": str(sale.id),
                "payout_received_at": (
                    None
                    if sale.payout_received_at is None
                    else sale.payout_received_at.isoformat()
                ),
            }
        )
