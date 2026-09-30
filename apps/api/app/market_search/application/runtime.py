"""Ce dont une recherche a besoin pour s'exécuter hors d'une requête HTTP.

Une recherche dure plusieurs secondes : elle ne doit jamais bloquer l'écran. Elle
tourne donc après la réponse, avec **sa propre** session de base et **ses
propres** sources. Ce couple est regroupé ici pour pouvoir être remplacé dans les
tests, où les sources sont simulées et la base est celle des tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collection.adapters.http_fetcher import USER_AGENT
from app.market_search.adapters.antiquorum import AntiquorumSource
from app.market_search.adapters.ebay_browse import EbayBrowseSource
from app.market_search.adapters.sworders import SwordersSource
from app.market_search.adapters.ucp_catalog import UcpCatalogSource
from app.market_search.adapters.vintage_watch_agency import VintageWatchAgencySource
from app.market_search.domain.policy import SearchPolicy
from app.market_search.ports.source import ComparableSource
from app.shared.config import Settings
from app.shared.infrastructure.db.session import get_session_factory
from app.shared.infrastructure.fx_ecb import refresh_ecb_rates

FxRefresh = Callable[[AsyncSession, set[str]], Awaitable[int]]
SourcesFactory = Callable[
    [Settings, SearchPolicy], AbstractAsyncContextManager[list[ComparableSource]]
]


@asynccontextmanager
async def default_sources(
    settings: Settings, policy: SearchPolicy
) -> AsyncIterator[list[ComparableSource]]:
    """Sources réelles. Seule eBay, par son API officielle, est validée."""

    marketplaces = [
        code.strip() for code in settings.ebay_marketplaces.split(",") if code.strip()
    ]
    enabled = {
        code.strip()
        for code in settings.market_search_sources.split(",")
        if code.strip()
    }
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(policy.request_timeout_s),
    ) as client:
        sources: list[ComparableSource] = []
        if "ebay" in enabled:
            sources.append(
                EbayBrowseSource(
                    client_id=(
                        settings.ebay_client_id.get_secret_value()
                        if settings.ebay_client_id
                        else None
                    ),
                    client_secret=(
                        settings.ebay_client_secret.get_secret_value()
                        if settings.ebay_client_secret
                        else None
                    ),
                    marketplaces=marketplaces,
                    policy=policy,
                    client=client,
                    environment=settings.ebay_environment,
                    base_url=settings.ebay_api_base_url,
                )
            )
        if "phigora" in enabled:
            sources.append(
                UcpCatalogSource(
                    client,
                    policy,
                    name="phigora",
                    site="https://www.phigora.com",
                    country="US",
                )
            )
        if "antiquorum" in enabled:
            sources.append(AntiquorumSource(client, policy))
        if "sworders" in enabled:
            sources.append(SwordersSource(client, policy))
        if "vintage_watch_agency" in enabled:
            sources.append(VintageWatchAgencySource(client, policy))
        yield sources


@dataclass(frozen=True, slots=True)
class SearchRuntime:
    session_factory: Callable[[], async_sessionmaker[AsyncSession]]
    sources: SourcesFactory
    policy: SearchPolicy = SearchPolicy()
    fx_refresh: FxRefresh = refresh_ecb_rates


def get_search_runtime() -> SearchRuntime:
    """Dépendance FastAPI, remplaçable dans les tests."""

    return SearchRuntime(session_factory=get_session_factory, sources=default_sources)
