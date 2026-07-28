from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.shared.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
    )
