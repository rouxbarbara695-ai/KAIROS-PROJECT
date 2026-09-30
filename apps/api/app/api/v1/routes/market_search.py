from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.market_search import (
    MarketSearchLatestResponse,
    MarketSearchStartRequest,
    MarketSearchStartResponse,
)
from app.market_search.application.presenters import to_run_response
from app.market_search.application.runtime import SearchRuntime, get_search_runtime
from app.market_search.application.search_run import (
    configured_source_names,
    execute_run,
    start_search,
)
from app.shared.config import Settings, get_settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.jobs import MarketSearchRun
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.watches import Watch
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.principal_provider import get_current_principal

router = APIRouter(tags=["market-search"])


@router.post(
    "/opportunities/{opportunity_id}/market-searches",
    response_model=MarketSearchStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_market_search(
    opportunity_id: uuid.UUID,
    body: MarketSearchStartRequest,
    background: BackgroundTasks,
    response: Response,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
    runtime: SearchRuntime = Depends(get_search_runtime),
) -> MarketSearchStartResponse:
    """Lance la recherche autonome de comparables et rend la main tout de suite.

    La recherche dure plusieurs secondes : elle s'exécute après la réponse, et
    l'écran relit son avancement. `202` quand elle démarre ; `200` quand la
    demande est ramenée à une recherche déjà en cours ou encore fraîche.
    """

    result = await start_search(
        session,
        principal,
        opportunity_id,
        settings,
        runtime,
        trigger="refresh",
        force=body.force,
    )
    if result.launched:
        background.add_task(execute_run, result.run.id, settings, runtime)
    else:
        response.status_code = status.HTTP_200_OK

    run = to_run_response(result.run, runtime.policy)
    return MarketSearchStartResponse(
        **run.model_dump(),
        launched=result.launched,
        reused=result.reused,
    )


@router.get(
    "/opportunities/{opportunity_id}/market-searches/latest",
    response_model=MarketSearchLatestResponse,
)
async def latest_market_search(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
    runtime: SearchRuntime = Depends(get_search_runtime),
) -> MarketSearchLatestResponse:
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

    run = None
    if watch.reference_id is not None:
        run = (
            await session.execute(
                select(MarketSearchRun)
                .where(
                    MarketSearchRun.portfolio_id == opportunity.portfolio_id,
                    MarketSearchRun.reference_id == watch.reference_id,
                )
                .order_by(MarketSearchRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    return MarketSearchLatestResponse(
        run=to_run_response(run, runtime.policy) if run else None,
        configured_sources=await configured_source_names(runtime, settings),
    )
