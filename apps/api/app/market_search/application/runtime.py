"""Ce dont une recherche a besoin pour s'exécuter hors d'une requête HTTP.

Une recherche dure plusieurs secondes : elle ne doit jamais bloquer l'écran. Elle
tourne donc après la réponse, avec **sa propre** session de base et **ses
propres** sources. Ce couple est regroupé ici pour pouvoir être remplacé dans les
tests, où les sources sont simulées et la base est celle des tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collection.adapters.http_fetcher import USER_AGENT
from app.market_search.adapters.ebay_browse import EbayBrowseSource
from app.market_search.domain.policy import SearchPolicy
from app.market_search.ports.source import ComparableSource
from app.shared.config import Settings
from app.shared.infrastructure.db.session import get_session_factory

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
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(policy.request_timeout_s),
    ) as client:
        yield [
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
            )
        ]


@dataclass(frozen=True, slots=True)
class SearchRuntime:
    session_factory: Callable[[], async_sessionmaker[AsyncSession]]
    sources: SourcesFactory
    policy: SearchPolicy = SearchPolicy()


def get_search_runtime() -> SearchRuntime:
    """Dépendance FastAPI, remplaçable dans les tests."""

    return SearchRuntime(session_factory=get_session_factory, sources=default_sources)
