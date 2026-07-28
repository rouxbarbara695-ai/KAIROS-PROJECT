from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.page import CursorPosition, Page, decode_cursor, encode_cursor
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.market import Comparable, ComparableOverride
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.watches import Watch


@dataclass(frozen=True, slots=True)
class ComparableView:
    """Comparable assorti de l'état courant de sa chaîne d'overrides."""

    comparable: Comparable
    excluded: bool
    exclusion_reason: str | None


async def _override_state(
    session: AsyncSession, comparable_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ComparableOverride]:
    if not comparable_ids:
        return {}

    successor = select(ComparableOverride.previous_override_id).where(
        ComparableOverride.comparable_id.in_(comparable_ids),
        ComparableOverride.previous_override_id.is_not(None),
    )

    rows = (
        await session.execute(
            select(ComparableOverride).where(
                ComparableOverride.comparable_id.in_(comparable_ids),
                ComparableOverride.id.not_in(successor),
            )
        )
    ).scalars()

    return {row.comparable_id: row for row in rows}


async def list_comparables(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> Page[ComparableView]:
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

    if watch.reference_id is None:
        return Page(items=[], next_cursor=None)

    query = select(Comparable).where(
        Comparable.portfolio_id == opportunity.portfolio_id,
        Comparable.reference_id == watch.reference_id,
    )

    if cursor is not None:
        position: CursorPosition = decode_cursor(cursor)
        query = query.where(
            or_(
                Comparable.created_at < position.created_at,
                and_(
                    Comparable.created_at == position.created_at,
                    Comparable.id < position.id,
                ),
            )
        )

    query = query.order_by(Comparable.created_at.desc(), Comparable.id.desc()).limit(
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

    overrides = await _override_state(session, [row.id for row in rows])

    items = []
    for row in rows:
        override = overrides.get(row.id)
        items.append(
            ComparableView(
                comparable=row,
                excluded=override.excluded if override else False,
                exclusion_reason=override.exclusion_reason if override else None,
            )
        )

    return Page(items=items, next_cursor=next_cursor)
