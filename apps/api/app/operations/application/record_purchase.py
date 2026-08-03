"""Enregistrement d'un achat (KAI-401).

L'achat est le pivot du cycle : il fait passer une intention en détention, il
sort la trésorerie et il fait entrer la montre au stock. Tant qu'il n'existe
pas, le portefeuille ne peut pas dire ce qu'il possède, et le pilier qui bloque
le plus souvent le verdict reste faux dès la deuxième montre.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operations.domain.workflow import ensure_transition
from app.portfolio.domain.ledger import LedgerKind
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.audit import AuditEvent
from app.shared.infrastructure.db.models.enums import OpportunityStatus
from app.shared.infrastructure.db.models.operations import Purchase
from app.shared.infrastructure.db.models.opportunities import (
    Opportunity,
    OpportunityEvent,
)
from app.shared.infrastructure.db.models.portfolio_ledger import PortfolioLedgerEntry
from app.shared.infrastructure.fx import resolve_fx


async def record_purchase(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    *,
    amount: Decimal,
    currency: str,
    purchased_at: datetime | None,
    reason: str,
    settings: Settings,
) -> Purchase:
    """Enregistre l'achat effectif d'une opportunité.

    Le montant demandé est celui **réellement payé**, pas le prix affiché ni le
    maximum calculé : reprendre l'un des deux ferait de KAIROS un outil qui se
    relit lui-même, et le coût de revient serait faux dès la première
    négociation réussie.

    L'écriture de trésorerie en découle, elle ne se saisit pas — c'est la
    frontière que `record_movement` fait déjà respecter en refusant la nature
    `purchase_payment` à la saisie manuelle. Les deux écritures partagent la
    même transaction : un achat sans sa sortie de trésorerie laisserait un
    portefeuille qui prétend détenir une montre sans l'avoir payée.
    """

    opportunity = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()

    if opportunity is None or not principal.owns_portfolio(opportunity.portfolio_id):
        # 404 et non 403 : l'existence d'une opportunité étrangère ne doit pas
        # se déduire de la différence de code.
        raise DomainError(ErrorCode.NOT_FOUND, "Opportunité introuvable.")

    ensure_transition(
        OpportunityStatus(opportunity.status), OpportunityStatus.PURCHASED
    )

    if amount <= 0:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Le montant payé doit être strictement positif.",
            field="amount",
        )

    if not reason.strip():
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Un motif est exigé : une transition sans motif rend l'historique "
            "incapable d'expliquer ce que le portefeuille détient.",
            field="reason",
        )

    when = purchased_at or datetime.now(UTC)
    if when > datetime.now(UTC):
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Un achat ne peut pas être daté dans le futur.",
            field="purchased_at",
        )

    fx = await resolve_fx(session, currency, settings.fx_max_age_hours)
    if fx is None:
        raise DomainError(
            ErrorCode.FX_RATE_UNAVAILABLE,
            f"Aucun taux de change récent pour {currency}.",
            field="currency",
        )

    amount_eur = fx.convert(amount)

    # Aucun contrôle de trésorerie disponible ici, à la différence d'un
    # retrait. Un achat est un fait accompli : refuser de l'enregistrer parce
    # que le registre ignore d'où venait l'argent ferait mentir l'outil sur ce
    # qu'on possède. Une trésorerie négative se lit alors comme ce qu'elle
    # est — un apport oublié — au lieu d'être masquée par un refus.
    purchase = Purchase(
        portfolio_id=opportunity.portfolio_id,
        opportunity_id=opportunity.id,
        amount_source=amount,
        currency=currency.upper(),
        amount_eur=amount_eur,
        rate_to_eur=fx.rate_to_eur,
        fx_rate_at=fx.fx_rate_at,
        fx_source=fx.fx_source,
        fx_rate_id=fx.fx_rate_id,
        purchased_at=when,
        created_by_user_id=principal.user_id,
    )
    session.add(purchase)

    session.add(
        PortfolioLedgerEntry(
            portfolio_id=opportunity.portfolio_id,
            opportunity_id=opportunity.id,
            kind=LedgerKind.PURCHASE_PAYMENT.value,
            amount_source=amount,
            currency=currency.upper(),
            amount_eur=amount_eur,
            rate_to_eur=fx.rate_to_eur,
            fx_rate_at=fx.fx_rate_at,
            fx_source=fx.fx_source,
            fx_rate_id=fx.fx_rate_id,
            occurred_at=when,
            notes=reason.strip(),
            actor_user_id=principal.user_id,
        )
    )

    previous = opportunity.status
    opportunity.status = OpportunityStatus.PURCHASED.value
    opportunity.version += 1

    session.add(
        OpportunityEvent(
            portfolio_id=opportunity.portfolio_id,
            opportunity_id=opportunity.id,
            actor_user_id=principal.user_id,
            event_type="purchase_recorded",
            from_status=previous,
            to_status=OpportunityStatus.PURCHASED.value,
            reason=reason.strip(),
            # Le montant en euros et sa traçabilité de change suffisent à
            # rejouer l'écriture. Rien d'autre n'entre ici : la charge utile
            # d'un événement est lue par des tiers, et le numéro de série n'y a
            # pas sa place (CLAUDE.md règle 11).
            payload={
                "amount_source": str(amount),
                "currency": currency.upper(),
                "amount_eur": str(amount_eur),
                "rate_to_eur": str(fx.rate_to_eur),
                "fx_source": fx.fx_source,
            },
            occurred_at=when,
        )
    )

    # Les deux écritures, comme l'exige `workflow-and-states.md` : l'événement
    # d'opportunité porte la transition, l'événement d'audit porte la trace
    # relue par l'historique de la fiche. N'écrire que la première rendrait
    # l'achat invisible là où l'utilisateur va le chercher.
    session.add(
        AuditEvent(
            portfolio_id=opportunity.portfolio_id,
            actor_user_id=principal.user_id,
            resource_type="opportunity",
            resource_id=opportunity.id,
            action="purchase_recorded",
            reason=reason.strip(),
            before_data={"status": previous},
            after_data={
                "status": OpportunityStatus.PURCHASED.value,
                "amount_eur": str(amount_eur),
                "currency": currency.upper(),
            },
            occurred_at=when,
        )
    )

    await session.commit()
    await session.refresh(purchase)
    return purchase
