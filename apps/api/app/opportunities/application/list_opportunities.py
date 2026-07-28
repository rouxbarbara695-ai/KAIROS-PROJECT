from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.page import CursorPosition, Page, decode_cursor, encode_cursor
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.watches import Watch, WatchReference


@dataclass(frozen=True, slots=True)
class OpportunityListFilters:
    status: str | None = None
    brand: str | None = None
    reference: str | None = None


async def list_opportunities(
    session: AsyncSession,
    principal: Principal,
    filters: OpportunityListFilters,
    limit: int,
    cursor: str | None,
) -> Page[Opportunity]:
    query = select(Opportunity).where(
        Opportunity.portfolio_id.in_(principal.portfolio_ids)
    )

    if filters.status is not None:
        query = query.where(Opportunity.status == filters.status)

    if filters.brand is not None or filters.reference is not None:
        query = query.join(Watch, Watch.id == Opportunity.watch_id).join(
            WatchReference, WatchReference.id == Watch.reference_id
        )
        if filters.brand is not None:
            query = query.where(WatchReference.brand.ilike(f"%{filters.brand}%"))
        if filters.reference is not None:
            query = query.where(
                WatchReference.reference.ilike(f"%{filters.reference}%")
            )

    if cursor is not None:
        position: CursorPosition = decode_cursor(cursor)
        query = query.where(
            or_(
                Opportunity.created_at < position.created_at,
                and_(
                    Opportunity.created_at == position.created_at,
                    Opportunity.id < position.id,
                ),
            )
        )

    query = query.order_by(Opportunity.created_at.desc(), Opportunity.id.desc()).limit(
        limit + 1
    )

    rows = list((await session.execute(query)).scalars().all())

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(
            CursorPosition(created_at=last.created_at, id=str(last.id))
        )

    return Page(items=rows, next_cursor=next_cursor)
