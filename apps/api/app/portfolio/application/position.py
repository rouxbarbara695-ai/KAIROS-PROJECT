from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.portfolio.domain.exposure import PortfolioPosition
from app.portfolio.domain.ledger import LedgerKind, LedgerMovement, cash_balance
from app.shared.infrastructure.db.models.operations import Purchase, Sale
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.portfolio_ledger import PortfolioLedgerEntry
from app.shared.infrastructure.db.models.watches import Watch, WatchReference


async def cash_available_eur(session: AsyncSession, portfolio_id: uuid.UUID) -> Decimal:
    """Trésorerie disponible, reconstruite depuis le registre.

    Elle n'est jamais stockée comme un solde : un solde entretenu diverge de
    ses mouvements dès la première écriture manquée. La recalculer garantit
    qu'elle s'explique toujours ligne à ligne.
    """

    rows = (
        await session.execute(
            select(PortfolioLedgerEntry.kind, PortfolioLedgerEntry.amount_eur).where(
                PortfolioLedgerEntry.portfolio_id == portfolio_id
            )
        )
    ).all()

    return cash_balance(
        LedgerMovement(kind=LedgerKind(kind), amount_eur=amount)
        for kind, amount in rows
    )


async def _stock_at_cost_eur(
    session: AsyncSession, portfolio_id: uuid.UUID, brand: str | None
) -> Decimal:
    """Coût d'acquisition des montres encore détenues.

    Au coût, jamais à l'estimation (cf. `PortfolioPosition`). Une opportunité
    vendue sort du stock : c'est la vente, pas la mise en vente, qui l'en fait
    sortir — tant que l'objet n'est pas parti, le capital reste immobilisé.
    """

    sold = select(Sale.opportunity_id).where(Sale.portfolio_id == portfolio_id)

    query = select(func.coalesce(func.sum(Purchase.amount_eur), Decimal("0"))).where(
        Purchase.portfolio_id == portfolio_id,
        Purchase.opportunity_id.notin_(sold),
    )

    if brand is not None:
        query = (
            query.join(Opportunity, Opportunity.id == Purchase.opportunity_id)
            .join(Watch, Watch.id == Opportunity.watch_id)
            .join(WatchReference, WatchReference.id == Watch.reference_id)
            .where(WatchReference.brand == brand)
        )

    return (await session.execute(query)).scalar_one()


async def current_position(
    session: AsyncSession, portfolio_id: uuid.UUID, brand: str | None
) -> PortfolioPosition:
    """Situation du portefeuille telle qu'une analyse doit la voir.

    `brand` est celle de la montre analysée : la concentration se mesure
    toujours par rapport à la marque envisagée, pas dans l'absolu.
    """

    cash = await cash_available_eur(session, portfolio_id)
    stock = await _stock_at_cost_eur(session, portfolio_id, brand=None)
    exposure = (
        await _stock_at_cost_eur(session, portfolio_id, brand=brand)
        if brand is not None
        else Decimal("0")
    )

    return PortfolioPosition(
        # Un découvert se constate dans le registre, mais aucune exposition ne
        # se mesure sur une trésorerie négative : le calcul s'arrêterait plus
        # loin sur une erreur moins lisible que celle-ci.
        available_cash_eur=max(cash, Decimal("0")),
        stock_at_cost_eur=stock,
        brand_exposure_at_cost_eur=exposure,
    )
