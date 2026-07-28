from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.comparables import (
    ComparableCreate,
    ComparablePage,
    ComparableResponse,
    OverrideCreate,
    OverrideResponse,
    ValuationResponse,
)
from app.market.application.comparable_overrides import apply_override
from app.market.application.compute_valuation import compute_valuation
from app.market.application.create_comparable import create_comparable
from app.market.application.list_comparables import ComparableView, list_comparables
from app.shared.config import Settings, get_settings
from app.shared.domain.page import clamp_limit
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.market import Comparable
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.principal_provider import get_current_principal

router = APIRouter(tags=["comparables"])

# Plafond de sécurité : au-delà, la cote signalerait un usage hors du cadre
# mono-organisation du MVP plutôt qu'un besoin légitime.
_VALUATION_MAX_COMPARABLES = 500


def _request_id(request: Request) -> uuid.UUID | None:
    raw = getattr(request.state, "request_id", None)
    try:
        return uuid.UUID(raw) if raw else None
    except ValueError:
        return None


def _to_response(
    comparable: Comparable, excluded: bool, exclusion_reason: str | None
) -> ComparableResponse:
    return ComparableResponse(
        id=comparable.id,
        source_name=comparable.source_name,
        price_kind=comparable.price_kind,
        amount_source=comparable.amount_source,
        currency=comparable.currency,
        amount_eur=comparable.amount_eur,
        rate_to_eur=comparable.rate_to_eur,
        fx_source=comparable.fx_source,
        fx_rate_at=comparable.fx_rate_at,
        buyer_total_price_eur=comparable.buyer_total_price_eur,
        market_status=comparable.market_status,
        observed_at=comparable.observed_at,
        listed_at=comparable.listed_at,
        ended_at=comparable.ended_at,
        source_reliability=comparable.source_reliability,
        condition_data=comparable.condition_data,
        completeness_data=comparable.completeness_data,
        excluded=excluded,
        exclusion_reason=exclusion_reason,
    )


@router.post(
    "/opportunities/{opportunity_id}/comparables",
    status_code=status.HTTP_201_CREATED,
    response_model=ComparableResponse,
)
async def create_comparable_route(
    opportunity_id: uuid.UUID,
    body: ComparableCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> ComparableResponse:
    comparable = await create_comparable(
        session, principal, opportunity_id, body, settings
    )
    return _to_response(comparable, excluded=False, exclusion_reason=None)


@router.get(
    "/opportunities/{opportunity_id}/comparables", response_model=ComparablePage
)
async def list_comparables_route(
    opportunity_id: uuid.UUID,
    limit: int | None = Query(default=None),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> ComparablePage:
    page = await list_comparables(
        session, principal, opportunity_id, clamp_limit(limit), cursor
    )
    return ComparablePage(
        items=[
            _to_response(view.comparable, view.excluded, view.exclusion_reason)
            for view in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/comparables/{comparable_id}/overrides",
    status_code=status.HTTP_201_CREATED,
    response_model=OverrideResponse,
)
async def create_override_route(
    comparable_id: uuid.UUID,
    body: OverrideCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> OverrideResponse:
    override = await apply_override(
        session, principal, comparable_id, body, _request_id(request)
    )
    return OverrideResponse(
        id=override.id,
        comparable_id=override.comparable_id,
        previous_override_id=override.previous_override_id,
        excluded=override.excluded,
        exclusion_reason=override.exclusion_reason,
        corrected_data=override.corrected_data,
        reason=override.reason,
        created_at=override.created_at,
    )


@router.post(
    "/opportunities/{opportunity_id}/valuations",
    status_code=status.HTTP_201_CREATED,
    response_model=ValuationResponse,
)
async def create_valuation_route(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> ValuationResponse:
    """Recalcule la cote. Chaque appel crée une version : une valorisation
    publiée n'est jamais écrasée (CLAUDE.md règle 4)."""

    # La cote porte sur l'ensemble des comparables de la référence, pas sur une
    # page : la pagination d'affichage ne doit pas amputer le calcul.
    page = await list_comparables(
        session, principal, opportunity_id, _VALUATION_MAX_COMPARABLES, None
    )

    valuation = await compute_valuation(
        session, principal, opportunity_id, settings, list(page.items)
    )

    return ValuationResponse(
        id=valuation.id,
        opportunity_id=valuation.opportunity_id,
        calculated_at=valuation.calculated_at,
        low_value_eur=valuation.low_value_eur,
        central_value_eur=valuation.central_value_eur,
        high_value_eur=valuation.high_value_eur,
        valuation_confidence=valuation.valuation_confidence,
        explanation=valuation.explanation,
    )


__all__ = ["ComparableView", "router"]
