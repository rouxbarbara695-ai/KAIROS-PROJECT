from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.portfolio.application.position import cash_available_eur
from app.portfolio.domain.ledger import TREASURY_KINDS, LedgerKind
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.portfolio_ledger import PortfolioLedgerEntry
from app.shared.infrastructure.fx import resolve_fx


async def record_movement(
    session: AsyncSession,
    principal: Principal,
    portfolio_id: uuid.UUID,
    *,
    kind: str,
    amount: Decimal,
    currency: str,
    occurred_at: datetime | None,
    notes: str | None,
    settings: Settings,
) -> PortfolioLedgerEntry:
    """Écrit un mouvement de trésorerie dans le registre.

    Le registre est append-only : on ne corrige pas une écriture, on en passe
    une autre en sens inverse. C'est ce qui permet à la trésorerie de
    s'expliquer ligne à ligne plutôt que de se contenter d'un solde.
    """

    if not principal.owns_portfolio(portfolio_id):
        # 404 et non 403 : l'existence d'un portefeuille étranger ne doit pas
        # être révélée par la différence de code.
        raise DomainError(ErrorCode.NOT_FOUND, "Portefeuille introuvable.")

    try:
        movement_kind = LedgerKind(kind)
    except ValueError as exc:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            f"Nature de mouvement inconnue : {kind}.",
            field="kind",
        ) from exc

    if movement_kind not in TREASURY_KINDS:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Cette nature de mouvement a une contrepartie dans les opérations "
            "d'achat ou de vente : la saisir à la main ferait diverger le "
            "registre de ce qu'il reflète.",
            field="kind",
        )

    if amount <= 0:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Le montant doit être strictement positif : c'est la nature du "
            "mouvement qui en porte le sens, pas le signe.",
            field="amount",
        )

    fx = await resolve_fx(session, currency, settings.fx_max_age_hours)
    if fx is None:
        raise DomainError(
            ErrorCode.FX_RATE_UNAVAILABLE,
            f"Aucun taux de change récent pour {currency}.",
            field="currency",
        )

    when = occurred_at or datetime.now(UTC)
    if when > datetime.now(UTC):
        # Un mouvement futur fausserait une trésorerie qu'on présente comme
        # disponible aujourd'hui.
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Un mouvement ne peut pas être daté dans le futur.",
            field="occurred_at",
        )

    amount_eur = fx.convert(amount)

    if movement_kind in (LedgerKind.WITHDRAWAL, LedgerKind.NEGATIVE_ADJUSTMENT):
        available = await cash_available_eur(session, portfolio_id)
        if amount_eur > available:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                "Ce retrait dépasse la trésorerie disponible "
                f"({available} €). Un découvert se constate, il ne se saisit "
                "pas.",
                field="amount",
                details={"available_cash_eur": str(available)},
            )

    entry = PortfolioLedgerEntry(
        portfolio_id=portfolio_id,
        kind=movement_kind.value,
        amount_source=amount,
        currency=currency.upper(),
        amount_eur=amount_eur,
        rate_to_eur=fx.rate_to_eur,
        fx_rate_at=fx.fx_rate_at,
        fx_source=fx.fx_source,
        fx_rate_id=fx.fx_rate_id,
        occurred_at=when,
        notes=notes,
        actor_user_id=principal.user_id,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry
