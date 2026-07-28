from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.infrastructure.db.models.platforms import Platform, PlatformRule


async def get_applicable_rule(
    session: AsyncSession, platform_code: str, region_code: str, at: datetime
) -> PlatformRule:
    platform = (
        await session.execute(select(Platform).where(Platform.code == platform_code))
    ).scalar_one_or_none()
    if platform is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Plateforme inconnue.")

    rule = (
        await session.execute(
            select(PlatformRule)
            .where(
                PlatformRule.platform_id == platform.id,
                PlatformRule.region_code.in_((region_code, "*")),
                PlatformRule.valid_from <= at,
                or_(PlatformRule.valid_to.is_(None), PlatformRule.valid_to > at),
            )
            .order_by(PlatformRule.region_code.desc(), PlatformRule.valid_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if rule is None:
        raise DomainError(
            ErrorCode.NOT_FOUND,
            "Aucune règle de plateforme applicable à cette date/région.",
        )
    return rule
