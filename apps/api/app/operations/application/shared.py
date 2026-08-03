"""Mécanique commune aux quatre étapes du cycle.

Achat, mise en vente, vente et encaissement partagent la même liturgie :
retrouver l'opportunité, vérifier la transition, exiger un motif, refuser une
date future, résoudre le change, puis écrire les deux événements. Chacune ne
diffère que par la ligne d'opération qu'elle produit.

Factoriser évite qu'une étape oublie un contrôle que les autres appliquent —
c'est exactement ainsi que la première version de l'achat avait omis
l'événement d'audit et rendu l'opération invisible dans l'historique.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operations.domain.workflow import ensure_transition
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.audit import AuditEvent
from app.shared.infrastructure.db.models.enums import OpportunityStatus
from app.shared.infrastructure.db.models.opportunities import (
    Opportunity,
    OpportunityEvent,
)
from app.shared.infrastructure.fx import FxResolution


@dataclass(frozen=True, slots=True)
class OperationContext:
    """Ce qu'une étape a besoin de savoir, une fois les contrôles passés."""

    opportunity: Opportunity
    previous_status: str
    when: datetime
    fx: FxResolution
    amount_eur: Decimal
    reason: str


async def load_for_transition(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    target: OpportunityStatus,
) -> Opportunity:
    """Retrouve l'opportunité et vérifie que la transition visée est prévue."""

    opportunity = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()

    if opportunity is None or not principal.owns_portfolio(opportunity.portfolio_id):
        # 404 et non 403 : l'existence d'une opportunité étrangère ne doit pas
        # se déduire de la différence de code.
        raise DomainError(ErrorCode.NOT_FOUND, "Opportunité introuvable.")

    ensure_transition(OpportunityStatus(opportunity.status), target)
    return opportunity


async def prepare(
    session: AsyncSession,
    opportunity: Opportunity,
    *,
    amount: Decimal,
    currency: str,
    occurred_at: datetime | None,
    reason: str,
    settings: Settings,
    amount_field: str = "amount",
    date_field: str = "occurred_at",
) -> OperationContext:
    """Contrôle le montant, le motif et la date, puis résout le change."""

    if amount <= 0:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Le montant doit être strictement positif.",
            field=amount_field,
        )

    if not reason.strip():
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Un motif est exigé : une transition sans motif rend l'historique "
            "incapable d'expliquer ce que le portefeuille détient.",
            field="reason",
        )

    when = occurred_at or datetime.now(UTC)
    if when > datetime.now(UTC):
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Une opération ne peut pas être datée dans le futur.",
            field=date_field,
        )

    from app.shared.infrastructure.fx import resolve_fx

    fx = await resolve_fx(session, currency, settings.fx_max_age_hours)
    if fx is None:
        # Jamais de conversion au petit bonheur : sans taux frais, le montant
        # en euros serait une invention (CLAUDE.md règle 3).
        raise DomainError(
            ErrorCode.FX_RATE_UNAVAILABLE,
            f"Aucun taux de change récent pour {currency}.",
            field="currency",
        )

    return OperationContext(
        opportunity=opportunity,
        previous_status=opportunity.status,
        when=when,
        fx=fx,
        amount_eur=fx.convert(amount),
        reason=reason.strip(),
    )


def apply_transition(
    session: AsyncSession,
    context: OperationContext,
    principal: Principal,
    *,
    target: OpportunityStatus,
    event_type: str,
    payload: dict[str, object],
) -> None:
    """Change le statut et écrit les deux événements.

    `workflow-and-states.md` exige les deux : l'événement d'opportunité porte
    la transition, l'événement d'audit porte la trace que relit l'historique de
    la fiche. N'écrire que le premier rendrait l'opération invisible là où
    l'utilisateur va la chercher.

    Aucune donnée sensible dans la charge utile : ni numéro de série, ni
    coordonnées d'acheteur (CLAUDE.md règle 11).
    """

    opportunity = context.opportunity
    opportunity.status = target.value
    opportunity.version += 1

    session.add(
        OpportunityEvent(
            portfolio_id=opportunity.portfolio_id,
            opportunity_id=opportunity.id,
            actor_user_id=principal.user_id,
            event_type=event_type,
            from_status=context.previous_status,
            to_status=target.value,
            reason=context.reason,
            payload=payload,
            occurred_at=context.when,
        )
    )
    session.add(
        AuditEvent(
            portfolio_id=opportunity.portfolio_id,
            actor_user_id=principal.user_id,
            resource_type="opportunity",
            resource_id=opportunity.id,
            action=event_type,
            reason=context.reason,
            before_data={"status": context.previous_status},
            after_data={"status": target.value, **payload},
            occurred_at=context.when,
        )
    )
