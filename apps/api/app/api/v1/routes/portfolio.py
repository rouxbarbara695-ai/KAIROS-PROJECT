from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.portfolio import (
    HoldingResponse,
    LedgerMovementCreate,
    LedgerMovementResponse,
    PortfolioOverviewResponse,
    StrategyResponse,
    StrategyUpdate,
)
from app.portfolio.application.position import overview
from app.portfolio.application.record_movement import record_movement
from app.scoring.application.strategy import (
    RESALE_PLATFORM,
    active_strategy_version,
    record_strategy_version,
)
from app.shared.config import Settings, get_settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.platforms import Platform
from app.shared.infrastructure.db.models.portfolio_ledger import PortfolioLedgerEntry
from app.shared.infrastructure.db.models.reference_data import Ruleset as RulesetRow
from app.shared.infrastructure.db.models.strategies import StrategyVersion
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


def _strategy(version: StrategyVersion) -> StrategyResponse:
    code = version.settings.get(RESALE_PLATFORM)
    return StrategyResponse(
        id=version.id,
        version=version.version,
        valid_from=version.valid_from,
        minimum_roi=version.minimum_roi,
        minimum_profit_eur=version.minimum_profit_eur,
        maximum_allocation_rate=version.maximum_allocation_rate,
        negotiation_buffer=version.negotiation_buffer,
        resale_platform_code=None if code is None else str(code),
    )


async def _ruleset_id(session: AsyncSession, version: str) -> uuid.UUID:
    row = (
        await session.execute(
            select(RulesetRow.id).where(RulesetRow.version == version)
        )
    ).scalar_one_or_none()
    if row is None:
        raise DomainError(ErrorCode.RULESET_MISSING, f"Ruleset {version} introuvable.")
    return row


@router.get("/portfolios/{portfolio_id}/strategy", response_model=StrategyResponse)
async def get_strategy_route(
    portfolio_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> StrategyResponse:
    if not principal.owns_portfolio(portfolio_id):
        raise DomainError(ErrorCode.NOT_FOUND, "Portefeuille introuvable.")

    ruleset_id = await _ruleset_id(session, settings.active_ruleset_version)
    version = await active_strategy_version(
        session, portfolio_id, ruleset_id, principal.user_id
    )
    await session.commit()
    return _strategy(version)


@router.post(
    "/portfolios/{portfolio_id}/strategy",
    status_code=status.HTTP_201_CREATED,
    response_model=StrategyResponse,
)
async def update_strategy_route(
    portfolio_id: uuid.UUID,
    body: StrategyUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> StrategyResponse:
    """Ouvre une nouvelle version de la stratégie.

    Une version n'est jamais réécrite : une analyse figée référence celle qui
    l'a produite, et la modifier rendrait ce verdict inexplicable après coup.
    """

    if not principal.owns_portfolio(portfolio_id):
        raise DomainError(ErrorCode.NOT_FOUND, "Portefeuille introuvable.")

    if body.resale_platform_code is not None:
        exists = (
            await session.execute(
                select(Platform.id).where(Platform.code == body.resale_platform_code)
            )
        ).scalar_one_or_none()
        if exists is None:
            raise DomainError(
                ErrorCode.NOT_FOUND,
                "Plateforme de revente inconnue.",
                field="resale_platform_code",
            )

    ruleset_id = await _ruleset_id(session, settings.active_ruleset_version)
    version = await record_strategy_version(
        session,
        portfolio_id,
        ruleset_id,
        principal.user_id,
        minimum_roi=body.minimum_roi,
        minimum_profit_eur=body.minimum_profit_eur,
        maximum_allocation_rate=body.maximum_allocation_rate,
        negotiation_buffer=body.negotiation_buffer,
        resale_platform_code=body.resale_platform_code,
        clear_resale_platform=body.clear_resale_platform,
    )
    return _strategy(version)
