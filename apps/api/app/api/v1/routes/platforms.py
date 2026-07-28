from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.platforms.application.platform_rules_lookup import get_applicable_rule
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.principal_provider import get_current_principal

router = APIRouter(tags=["platforms"])


@router.get("/platforms/{code}/rules")
async def get_platform_rules_route(
    code: str,
    region: str = Query(default="*"),
    at: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    rule = await get_applicable_rule(session, code, region, at or datetime.now(UTC))
    return {
        "platform_code": code,
        "region_code": rule.region_code,
        "version": rule.version,
        "valid_from": rule.valid_from.isoformat(),
        "valid_to": rule.valid_to.isoformat() if rule.valid_to else None,
        "access_method": rule.access_method,
        "access_authorized": rule.access_authorized,
        "buyer_fee_rate": str(rule.buyer_fee_rate) if rule.buyer_fee_rate else None,
        "seller_fee_rate": str(rule.seller_fee_rate) if rule.seller_fee_rate else None,
    }
