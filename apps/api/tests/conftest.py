from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.shared.infrastructure.db.session import get_session

_ADMIN_DSN = "postgresql://kairos:kairos@localhost:5432/postgres"
_TEST_DB_NAME = "kairos_test"
_TEST_DATABASE_URL = (
    f"postgresql+psycopg://kairos:kairos@localhost:5432/{_TEST_DB_NAME}"
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _REPO_ROOT / "apps" / "api" / "alembic.ini"

# Tables métier réinitialisées entre deux tests. Les seeds de référence
# (platforms, rulesets) sont conservées, ainsi que `users`/`portfolios`/
# `portfolio_members` : ces trois tables sont référencées (FK) par `rulesets`
# et `platform_rules`, et TRUNCATE ... CASCADE se propage aux tables qui les
# référencent — les tronquer effacerait donc aussi les seeds de référence,
# même pour des lignes dont la FK est `null`. Le principal de développement
# et son portefeuille par défaut restent stables sur toute la session ; seule
# la donnée métier qu'ils possèdent est réinitialisée ci-dessous.
_TRUNCATE_TABLES = (
    "alerts",
    "telemetry_events",
    "collection_jobs",
    "idempotency_records",
    "portfolio_ledger_entries",
    "sales",
    "sale_listings",
    "purchases",
    "opportunity_costs",
    "analyses",
    "valuation_comparables",
    "market_valuations",
    "comparable_overrides",
    "comparables",
    "audit_events",
    "opportunity_events",
    "reference_confirmations",
    "opportunity_price_inputs",
    "opportunities",
    "listing_observation_prices",
    "listing_observations",
    "listings",
    "sellers",
    "watches",
    "watch_references",
    "strategy_versions",
    "strategies",
    "fx_rates",
    "platform_rules",
)


@pytest.fixture(scope="session")
def _test_database() -> Iterator[None]:
    with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}"')
        conn.execute(f'CREATE DATABASE "{_TEST_DB_NAME}" OWNER kairos')

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", _TEST_DATABASE_URL)
    command.upgrade(cfg, "head")

    yield

    with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}"')


@pytest_asyncio.fixture(scope="session")
async def _engine(_test_database: None) -> AsyncIterator[object]:
    engine = create_async_engine(_TEST_DATABASE_URL)
    yield engine
    # Sans dispose(), une connexion du pool reste ouverte et le DROP DATABASE
    # de `_test_database` échoue en fin de session (ObjectInUse).
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_database(_engine) -> AsyncIterator[None]:
    yield
    async with _engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {', '.join(_TRUNCATE_TABLES)} CASCADE")
        )


@pytest_asyncio.fixture
async def db_session(_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(bind=_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(_engine) -> AsyncIterator[AsyncClient]:
    factory = async_sessionmaker(bind=_engine, expire_on_commit=False)

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def default_portfolio_id(
    client: AsyncClient, db_session: AsyncSession
) -> uuid.UUID:
    """Déclenche le bootstrap du principal de développement (première requête
    authentifiée) puis relit l'identifiant de son portefeuille par défaut.

    Filtré par nom : `users`/`portfolios` ne sont pas réinitialisés entre les
    tests (voir `_TRUNCATE_TABLES`), et certains tests de
    `test_migrations.py` insèrent leurs propres portefeuilles isolés — un
    `select(Portfolio.id)` sans filtre choisirait une ligne arbitraire."""

    from sqlalchemy import select

    from app.shared.infrastructure.db.models.accounts import Portfolio
    from app.shared.infrastructure.principal_provider import _DEFAULT_PORTFOLIO_NAME

    response = await client.get("/api/v1/opportunities")
    assert response.status_code == 200

    portfolio_id = (
        await db_session.execute(
            select(Portfolio.id).where(Portfolio.name == _DEFAULT_PORTFOLIO_NAME)
        )
    ).scalar_one_or_none()
    assert portfolio_id is not None
    return portfolio_id
