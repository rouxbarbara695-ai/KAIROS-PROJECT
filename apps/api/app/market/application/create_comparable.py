from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.comparables import ComparableCreate
from app.identity.domain import vocabularies as vocab
from app.market.domain.comparable import BuyerFeeRule, buyer_total_price
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.market import Comparable
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.watches import Watch
from app.shared.infrastructure.fx import resolve_fx


async def create_comparable(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    request: ComparableCreate,
    settings: Settings,
) -> Comparable:
    """Enregistre un comparable rattaché à la référence de l'opportunité.

    Le coût acheteur est calculé et figé à l'enregistrement : c'est lui, et non
    le prix affiché, qui sert de base économique à la cote (calculation-spec.md
    § 2). Les frais fournis sont ceux réellement constatés sur l'annonce ; la
    grille de plateforme n'est pas appliquée d'office, faute de savoir de quelle
    plateforme provient une saisie manuelle.
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

    watch = (
        await session.execute(select(Watch).where(Watch.id == opportunity.watch_id))
    ).scalar_one()

    if watch.reference_id is None:
        raise DomainError(
            ErrorCode.REFERENCE_UNCONFIRMED,
            "Un comparable doit se rattacher à une référence identifiée.",
            field="reference_id",
        )

    fx = await resolve_fx(session, request.currency, settings.fx_max_age_hours)
    if fx is None:
        raise DomainError(
            ErrorCode.FX_RATE_UNAVAILABLE,
            f"Aucun taux {request.currency}→EUR suffisamment récent.",
            field="currency",
            details={"currency": request.currency},
        )

    amount_eur = fx.convert(request.amount)

    variable_fee = request.buyer_variable_fee_eur or Decimal("0")
    fixed_fee = request.buyer_fixed_fee_eur or Decimal("0")
    shipping = request.compulsory_shipping_eur or Decimal("0")

    # Les frais sont déjà connus en euros : la grille sert ici de simple
    # véhicule pour réutiliser le calcul et ses garde-fous.
    cost = buyer_total_price(
        amount_eur,
        BuyerFeeRule(fixed=variable_fee + fixed_fee),
        compulsory_shipping_not_included_eur=shipping,
    )

    comparable = Comparable(
        portfolio_id=opportunity.portfolio_id,
        reference_id=watch.reference_id,
        source_name=request.source_name,
        source_external_id=request.source_external_id,
        seller_fingerprint=request.seller_fingerprint,
        price_kind=request.price_kind,
        amount_source=request.amount,
        currency=request.currency.upper(),
        amount_eur=amount_eur,
        rate_to_eur=fx.rate_to_eur,
        fx_rate_at=fx.fx_rate_at,
        fx_source=fx.fx_source,
        fx_rate_id=fx.fx_rate_id,
        buyer_variable_fee_eur=variable_fee,
        buyer_fixed_fee_eur=fixed_fee,
        compulsory_shipping_eur=shipping,
        buyer_total_price_eur=cost.total_eur,
        market_status=request.market_status,
        listed_at=request.listed_at,
        ended_at=request.ended_at,
        observed_at=request.observed_at,
        source_reliability=request.source_reliability,
        condition_data={
            "mechanical": vocab.normalize(
                request.mechanical_condition,
                vocab.MECHANICAL_CONDITIONS,
                vocab.MECHANICAL_FALLBACK,
            ),
            "cosmetic": vocab.normalize(
                request.cosmetic_condition,
                vocab.COSMETIC_CONDITIONS,
                vocab.COSMETIC_FALLBACK,
            ),
        },
        completeness_data={
            "level": vocab.completeness_level(request.box, request.papers)
        },
        raw_data=request.model_dump(mode="json"),
        created_by_user_id=principal.user_id,
    )

    session.add(comparable)
    await session.commit()
    await session.refresh(comparable)
    return comparable
