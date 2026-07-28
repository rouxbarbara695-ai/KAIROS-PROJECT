from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.page import CursorPosition, Page, decode_cursor, encode_cursor
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.audit import AuditEvent
from app.shared.infrastructure.db.models.market import Comparable
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.watches import Watch


async def list_opportunity_events(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> Page[AuditEvent]:
    """Historique métier et audit d'une opportunité
    (docs/architecture/api-contract.md).

    Les corrections sont tracées sur trois ressources distinctes — l'opportunité
    elle-même, sa montre et son vendeur. L'historique les réunit, car du point de
    vue de l'utilisateur il n'existe qu'un seul dossier.
    """

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

    # Le couple (type, identifiant) est comparé en entier : deux ressources de
    # types différents pourraient théoriquement porter le même identifiant.
    targets = [
        and_(
            AuditEvent.resource_type == "opportunity",
            AuditEvent.resource_id == opportunity.id,
        ),
        and_(
            AuditEvent.resource_type == "watch",
            AuditEvent.resource_id == opportunity.watch_id,
        ),
    ]
    if opportunity.seller_id is not None:
        targets.append(
            and_(
                AuditEvent.resource_type == "seller",
                AuditEvent.resource_id == opportunity.seller_id,
            )
        )

    # Les comparables se rattachent à la référence, pas à l'opportunité : les
    # exclure ou les réintégrer change pourtant la cote de ce dossier, donc ces
    # décisions appartiennent à son historique.
    watch = (
        await session.execute(select(Watch).where(Watch.id == opportunity.watch_id))
    ).scalar_one()

    if watch.reference_id is not None:
        comparable_ids = select(Comparable.id).where(
            Comparable.portfolio_id == opportunity.portfolio_id,
            Comparable.reference_id == watch.reference_id,
        )
        targets.append(
            and_(
                AuditEvent.resource_type == "comparable",
                AuditEvent.resource_id.in_(comparable_ids),
            )
        )

    query = select(AuditEvent).where(
        AuditEvent.portfolio_id == opportunity.portfolio_id,
        or_(*targets),
    )

    if cursor is not None:
        position: CursorPosition = decode_cursor(cursor)
        query = query.where(
            or_(
                AuditEvent.occurred_at < position.created_at,
                and_(
                    AuditEvent.occurred_at == position.created_at,
                    AuditEvent.id < position.id,
                ),
            )
        )

    query = query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(
        limit + 1
    )

    rows = list((await session.execute(query)).scalars().all())

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor(
            CursorPosition(created_at=last.occurred_at, id=str(last.id))
        )

    return Page(items=rows, next_cursor=next_cursor)
