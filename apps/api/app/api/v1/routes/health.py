from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.db.session import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("select 1"))
    return {"status": "ok", "database": "ok"}
