from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.portfolio import (
    HoldingResponse,
    LedgerMovementCreate,
    LedgerMovementResponse,
    PortfolioOverviewResponse,
)
from app.portfolio.application.position import overview
from app.portfolio.application.record_movement import record_movement
from app.shared.config import Settings, get_settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.portfolio_ledger import PortfolioLedgerEntry
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.principal_provider import get_current_principal

router = APIRouter(tags=["portfolio"])


def _movement(entry: PortfolioLedgerEntry) -> LedgerMovementResponse:
    return LedgerMovementResponse(
        id=entry.id,
        kind=entry.kind,
        amount_source=entry.amount_source,
        currency=entry.currency,
        amount_eur=entry.amount_eur,
        rate_to_eur=entry.rate_to_eur,
        fx_source=entry.fx_source,
        fx_rate_at=entry.fx_rate_at,
        occurred_at=entry.occurred_at,
        notes=entry.notes,
        created_at=entry.created_at,
    )


@router.get(
    "/portfolios/{portfolio_id}/overview", response_model=PortfolioOverviewResponse
)
async def get_portfolio_overview_route(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> PortfolioOverviewResponse:
    if not principal.owns_portfolio(portfolio_id):
        raise DomainError(ErrorCode.NOT_FOUND, "Portefeuille introuvable.")

    result = await overview(session, portfolio_id)

    return PortfolioOverviewResponse(
        portfolio_id=portfolio_id,
        available_cash_eur=result.available_cash_eur,
        stock_at_cost_eur=result.stock_at_cost_eur,
        total_capital_eur=result.total_capital_eur,
        holdings=[
            HoldingResponse(
                opportunity_id=holding.opportunity_id,
                brand=holding.brand,
                reference=holding.reference,
                cost_eur=holding.cost_eur,
                purchased_at=holding.purchased_at,
            )
            for holding in result.holdings
        ],
        movements=[_movement(entry) for entry in result.movements],
    )


@router.post(
    "/portfolios/{portfolio_id}/ledger-entries",
    status_code=status.HTTP_201_CREATED,
    response_model=LedgerMovementResponse,
)
async def create_ledger_entry_route(
    portfolio_id: uuid.UUID,
    body: LedgerMovementCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> LedgerMovementResponse:
    """Ajoute un mouvement de trésorerie.

    Le registre est append-only : on ne corrige pas une écriture, on en passe
    une autre en sens inverse. C'est ce qui permet à la trésorerie de
    s'expliquer ligne à ligne.
    """

    entry = await record_movement(
        session,
        principal,
        portfolio_id,
        kind=body.kind,
        amount=body.amount,
        currency=body.currency,
        occurred_at=body.occurred_at,
        notes=body.notes,
        settings=settings,
    )
    return _movement(entry)
