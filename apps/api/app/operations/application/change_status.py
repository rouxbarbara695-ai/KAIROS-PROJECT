"""Transition de statut motivée.

Les transitions qui ne portent aucune donnée propre — passer en intention
d'achat, abandonner, rouvrir — se font ici. Celles qui créent une opération
— achat, mise en vente, vente — ont leur propre cas d'usage, parce qu'elles
écrivent aussi une ligne d'opération et une écriture de trésorerie que le
statut seul ne suffirait pas à produire.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operations.domain.workflow import ensure_transition
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.audit import AuditEvent
from app.shared.infrastructure.db.models.enums import OpportunityStatus
from app.shared.infrastructure.db.models.opportunities import (
    Opportunity,
    OpportunityEvent,
)

# Ces statuts constatent une opération : les atteindre exige d'écrire aussi
# l'achat ou la vente correspondante. Les autoriser ici produirait un
# portefeuille qui se dit détenteur d'une montre dont aucune ligne d'achat
# n'existe, et dont la trésorerie n'a jamais bougé.
_REQUIRE_AN_OPERATION = frozenset(
    {
        OpportunityStatus.PURCHASED,
        OpportunityStatus.SOLD,
    }
)


async def change_status(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    *,
    target: str,
    reason: str,
) -> Opportunity:
    """Change le statut d'une opportunité, avec motif obligatoire."""

    opportunity = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()

    if opportunity is None or not principal.owns_portfolio(opportunity.portfolio_id):
        raise DomainError(ErrorCode.NOT_FOUND, "Opportunité introuvable.")

    try:
        wanted = OpportunityStatus(target)
    except ValueError as exc:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            f"Statut inconnu : {target}.",
            field="status",
        ) from exc

    if not reason.strip():
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Un motif est exigé : une transition sans motif rend l'historique "
            "incapable d'expliquer ce que le portefeuille détient.",
            field="reason",
        )

    ensure_transition(OpportunityStatus(opportunity.status), wanted)

    if wanted in _REQUIRE_AN_OPERATION:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            f"Le statut « {wanted.value} » constate une opération : il "
            "s'obtient en enregistrant l'achat ou la vente, pas en changeant "
            "le statut.",
            field="status",
        )

    now = datetime.now(UTC)
    previous = opportunity.status
    opportunity.status = wanted.value
    opportunity.version += 1

    session.add(
        OpportunityEvent(
            portfolio_id=opportunity.portfolio_id,
            opportunity_id=opportunity.id,
            actor_user_id=principal.user_id,
            event_type="status_changed",
            from_status=previous,
            to_status=wanted.value,
            reason=reason.strip(),
            occurred_at=now,
        )
    )

    # `workflow-and-states.md` exige les deux : la transition et sa trace
    # d'audit. L'historique de la fiche lit la seconde.
    session.add(
        AuditEvent(
            portfolio_id=opportunity.portfolio_id,
            actor_user_id=principal.user_id,
            resource_type="opportunity",
            resource_id=opportunity.id,
            action="status_changed",
            reason=reason.strip(),
            before_data={"status": previous},
            after_data={"status": wanted.value},
            occurred_at=now,
        )
    )

    await session.commit()
    await session.refresh(opportunity)
    return opportunity
