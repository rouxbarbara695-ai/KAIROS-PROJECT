from __future__ import annotations

from fastapi import APIRouter, Depends

from app.shared.domain.principal import Principal
from app.shared.infrastructure.principal_provider import get_current_principal

router = APIRouter(tags=["me"])


@router.get("/me")
async def get_me_route(
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    return {
        "user_id": str(principal.user_id),
        "portfolio_ids": [str(pid) for pid in principal.portfolio_ids],
    }
