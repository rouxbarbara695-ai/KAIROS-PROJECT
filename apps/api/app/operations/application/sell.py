"""Mise en vente, vente et encaissement (KAI-402).

Trois étapes distinctes parce que trois faits distincts, que la spécification
sépare et que confondre fausserait la trésorerie :

- **mise en vente** — on publie un prix demandé, rien n'a changé de main ;
- **vente** — un acheteur s'est engagé et la montre part, mais les fonds sont
  encore retenus par la plateforme ;
- **encaissement** — l'argent arrive, et c'est seulement là que la trésorerie
  bouge.

Écrire l'encaissement au moment de la vente ferait apparaître une trésorerie
qu'on n'a pas encore, parfois pendant des semaines.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operations.application.shared import (
    apply_transition,
    load_for_transition,
    prepare,
)
from app.portfolio.domain.ledger import LedgerKind
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.enums import ListingStatus, OpportunityStatus
from app.shared.infrastructure.db.models.operations import Sale, SaleListing
from app.shared.infrastructure.db.models.platforms import Platform
from app.shared.infrastructure.db.models.portfolio_ledger import PortfolioLedgerEntry


async def record_sale_listing(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    *,
    asking_amount: Decimal,
    currency: str,
    platform_code: str | None,
    external_url: str | None,
    listed_at: datetime | None,
    reason: str,
    settings: Settings,
) -> SaleListing:
    """Met la montre en vente : canal et prix demandé.

    Le prix demandé n'est pas le prix d'affichage recommandé par l'analyse. On
    peut viser plus haut pour se laisser de la marge, ou plus bas pour partir
    vite : c'est une décision commerciale, et l'enregistrer telle quelle est la
    seule façon de mesurer après coup si elle était bonne.
    """

    opportunity = await load_for_transition(
        session, principal, opportunity_id, OpportunityStatus.LISTED_FOR_SALE
    )

    platform_id: uuid.UUID | None = None
    if platform_code is not None:
        platform = (
            await session.execute(
                select(Platform).where(Platform.code == platform_code)
            )
        ).scalar_one_or_none()
        if platform is None:
            raise DomainError(
                ErrorCode.NOT_FOUND,
                f"Plateforme inconnue : {platform_code}.",
                field="platform_code",
            )
        platform_id = platform.id

    context = await prepare(
        session,
        opportunity,
        amount=asking_amount,
        currency=currency,
        occurred_at=listed_at,
        reason=reason,
        settings=settings,
        amount_field="asking_amount",
        date_field="listed_at",
    )

    listing = SaleListing(
        portfolio_id=opportunity.portfolio_id,
        opportunity_id=opportunity.id,
        platform_id=platform_id,
        asking_amount_source=asking_amount,
        currency=currency.upper(),
        asking_amount_eur=context.amount_eur,
        rate_to_eur=context.fx.rate_to_eur,
        fx_rate_at=context.fx.fx_rate_at,
        fx_source=context.fx.fx_source,
        fx_rate_id=context.fx.fx_rate_id,
        listed_at=context.when,
        external_url=external_url,
        status=ListingStatus.ACTIVE.value,
        created_by_user_id=principal.user_id,
    )
    session.add(listing)

    apply_transition(
        session,
        context,
        principal,
        target=OpportunityStatus.LISTED_FOR_SALE,
        event_type="listed_for_sale",
        payload={
            "asking_amount_eur": str(context.amount_eur),
            "currency": currency.upper(),
            "platform_code": platform_code,
        },
    )

    await session.commit()
    await session.refresh(listing)
    return listing


async def record_sale(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    *,
    realized_amount: Decimal,
    currency: str,
    sold_at: datetime | None,
    reason: str,
    settings: Settings,
) -> Sale:
    """Enregistre la vente : prix réalisé, montre partie, fonds retenus.

    Aucune écriture de trésorerie ici. La plateforme retient les fonds jusqu'à
    la livraison ; les compter maintenant ferait apparaître un argent dont on
    ne dispose pas, et le pilier portefeuille s'en trouverait faussé dans le
    sens le plus dangereux — celui qui autorise un achat de plus.
    """

    opportunity = await load_for_transition(
        session, principal, opportunity_id, OpportunityStatus.AWAITING_PAYOUT
    )

    context = await prepare(
        session,
        opportunity,
        amount=realized_amount,
        currency=currency,
        occurred_at=sold_at,
        reason=reason,
        settings=settings,
        amount_field="realized_amount",
        date_field="sold_at",
    )

    listing = (
        await session.execute(
            select(SaleListing)
            .where(SaleListing.opportunity_id == opportunity.id)
            .order_by(SaleListing.listed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if listing is not None:
        listing.status = ListingStatus.SOLD.value
        listing.ended_at = context.when

    sale = Sale(
        portfolio_id=opportunity.portfolio_id,
        opportunity_id=opportunity.id,
        sale_listing_id=None if listing is None else listing.id,
        realized_amount_source=realized_amount,
        currency=currency.upper(),
        realized_amount_eur=context.amount_eur,
        rate_to_eur=context.fx.rate_to_eur,
        fx_rate_at=context.fx.fx_rate_at,
        fx_source=context.fx.fx_source,
        fx_rate_id=context.fx.fx_rate_id,
        sold_at=context.when,
        created_by_user_id=principal.user_id,
    )
    session.add(sale)

    apply_transition(
        session,
        context,
        principal,
        target=OpportunityStatus.AWAITING_PAYOUT,
        event_type="sale_recorded",
        payload={
            "realized_amount_eur": str(context.amount_eur),
            "currency": currency.upper(),
        },
    )

    await session.commit()
    await session.refresh(sale)
    return sale


async def record_payout(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    *,
    amount: Decimal | None,
    currency: str | None,
    received_at: datetime | None,
    reason: str,
    settings: Settings,
) -> Sale:
    """Constate l'encaissement : c'est ici, et seulement ici, que la trésorerie
    monte.

    Le montant encaissé peut différer du prix réalisé — la plateforme prélève
    sa commission avant de reverser. On saisit donc ce qui est **réellement
    arrivé sur le compte** ; à défaut, le prix réalisé sert de valeur, ce qui
    correspond à une vente sans intermédiaire.

    L'écart entre les deux est précisément ce que la grille de frais prétend
    prévoir. Le conserver permettra un jour de confronter la prévision au
    relevé plutôt que de la croire sur parole.
    """

    opportunity = await load_for_transition(
        session, principal, opportunity_id, OpportunityStatus.SOLD
    )

    sale = (
        await session.execute(select(Sale).where(Sale.opportunity_id == opportunity.id))
    ).scalar_one_or_none()

    if sale is None:
        # Ne devrait pas arriver : `awaiting_payout` s'atteint en enregistrant
        # la vente. Le dire explicitement plutôt que de planter sur un `None`.
        raise DomainError(
            ErrorCode.INVALID_TRANSITION,
            "Aucune vente enregistrée pour cette opportunité.",
        )

    if sale.payout_received_at is not None:
        raise DomainError(
            ErrorCode.INVALID_TRANSITION,
            "L'encaissement de cette vente est déjà constaté.",
        )

    context = await prepare(
        session,
        opportunity,
        amount=sale.realized_amount_source if amount is None else amount,
        currency=sale.currency if currency is None else currency,
        occurred_at=received_at,
        reason=reason,
        settings=settings,
        date_field="received_at",
    )

    if context.when < sale.sold_at:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "L'encaissement ne peut pas précéder la vente.",
            field="received_at",
        )

    sale.payout_received_at = context.when

    session.add(
        PortfolioLedgerEntry(
            portfolio_id=opportunity.portfolio_id,
            opportunity_id=opportunity.id,
            kind=LedgerKind.SALE_RECEIPT.value,
            amount_source=sale.realized_amount_source if amount is None else amount,
            currency=(sale.currency if currency is None else currency).upper(),
            amount_eur=context.amount_eur,
            rate_to_eur=context.fx.rate_to_eur,
            fx_rate_at=context.fx.fx_rate_at,
            fx_source=context.fx.fx_source,
            fx_rate_id=context.fx.fx_rate_id,
            occurred_at=context.when,
            notes=context.reason,
            actor_user_id=principal.user_id,
        )
    )

    apply_transition(
        session,
        context,
        principal,
        target=OpportunityStatus.SOLD,
        event_type="payout_received",
        payload={
            "received_amount_eur": str(context.amount_eur),
            "realized_amount_eur": str(sale.realized_amount_eur),
        },
    )

    await session.commit()
    await session.refresh(sale)
    return sale
