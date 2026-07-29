from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.opportunities import CreateOpportunityRequest
from app.identity.domain import vocabularies as vocab
from app.identity.domain.seller import reliability_data
from app.opportunities.domain.canonical_url import canonicalize_url
from app.platforms.application.detect_platform import detect_platform_code
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.listings import Listing
from app.shared.infrastructure.db.models.opportunities import (
    Opportunity,
    OpportunityPriceInput,
)
from app.shared.infrastructure.db.models.platforms import Platform
from app.shared.infrastructure.db.models.watches import Seller, Watch, WatchReference
from app.shared.infrastructure.fx import resolve_fx


@dataclass(slots=True)
class CreateOpportunityResult:
    opportunity: Opportunity
    watch: Watch
    reference: WatchReference | None
    seller: Seller | None
    price_input: OpportunityPriceInput | None
    warnings: list[str] = field(default_factory=list)


async def _get_or_create_watch_reference(
    session: AsyncSession, brand: str, reference: str
) -> WatchReference:
    existing = (
        await session.execute(
            select(WatchReference).where(
                WatchReference.brand == brand, WatchReference.reference == reference
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    created = WatchReference(brand=brand, reference=reference)
    session.add(created)
    await session.flush()
    return created


async def create_opportunity(
    session: AsyncSession,
    principal: Principal,
    request: CreateOpportunityRequest,
    settings: Settings,
) -> CreateOpportunityResult:
    if not principal.owns_portfolio(request.portfolio_id):
        raise DomainError(
            ErrorCode.FORBIDDEN, "Ce portefeuille n'appartient pas au principal."
        )

    watch_reference = await _get_or_create_watch_reference(
        session, request.watch.brand, request.watch.reference
    )

    mechanical = vocab.normalize(
        request.watch.mechanical_condition,
        vocab.MECHANICAL_CONDITIONS,
        vocab.MECHANICAL_FALLBACK,
    )
    cosmetic = vocab.normalize(
        request.watch.cosmetic_condition,
        vocab.COSMETIC_CONDITIONS,
        vocab.COSMETIC_FALLBACK,
    )
    originality = vocab.normalize(
        request.watch.originality, vocab.ORIGINALITY_LEVELS, vocab.ORIGINALITY_FALLBACK
    )
    completeness = vocab.completeness_level(request.watch.box, request.watch.papers)

    watch = Watch(
        reference_id=watch_reference.id,
        reference_status=request.watch.reference_status,
        condition_data={
            "mechanical": mechanical,
            "cosmetic": cosmetic,
            "originality": originality,
        },
        completeness_data={"level": completeness},
        raw_input={
            "mechanical_condition": request.watch.mechanical_condition,
            "cosmetic_condition": request.watch.cosmetic_condition,
            "originality": request.watch.originality,
            "box": request.watch.box,
            "papers": request.watch.papers,
        },
    )
    session.add(watch)
    await session.flush()

    seller: Seller | None = None
    if any(
        value is not None
        for value in (
            request.seller.country_code,
            request.seller.seller_type,
            request.seller.reliability,
            request.seller.risk_level,
            request.seller.transaction_protections,
        )
    ):
        seller_type = vocab.normalize(
            request.seller.seller_type, vocab.SELLER_TYPES, vocab.SELLER_TYPE_FALLBACK
        )
        seller = Seller(
            portfolio_id=request.portfolio_id,
            country_code=request.seller.country_code,
            seller_type=seller_type,
            reliability_data=reliability_data(
                reliability=request.seller.reliability,
                risk_level=request.seller.risk_level,
                transaction_protections=request.seller.transaction_protections,
            ),
        )
        session.add(seller)
        await session.flush()

    listing: Listing | None = None
    if request.source.mode == "manual":
        existing_opportunity = (
            await session.execute(
                select(Opportunity).where(
                    Opportunity.portfolio_id == request.portfolio_id,
                    Opportunity.manual_identifier == request.source.manual_identifier,
                )
            )
        ).scalar_one_or_none()
        if existing_opportunity is not None:
            raise DomainError(
                ErrorCode.OPPORTUNITY_DUPLICATE,
                "Un identifiant manuel identique existe déjà dans ce portefeuille.",
                details={
                    "existing_opportunity_id": str(existing_opportunity.id),
                    "matched_on": "manual_identifier",
                },
            )
    else:
        assert request.source.url is not None
        canonical_url = canonicalize_url(request.source.url)
        existing_listing = (
            await session.execute(
                select(Listing).where(
                    Listing.portfolio_id == request.portfolio_id,
                    Listing.canonical_url == canonical_url,
                )
            )
        ).scalar_one_or_none()
        if existing_listing is not None:
            existing_opportunity = (
                await session.execute(
                    select(Opportunity).where(
                        Opportunity.portfolio_id == request.portfolio_id,
                        Opportunity.listing_id == existing_listing.id,
                    )
                )
            ).scalar_one_or_none()
            raise DomainError(
                ErrorCode.OPPORTUNITY_DUPLICATE,
                "Cette URL est déjà suivie dans ce portefeuille.",
                details={
                    "existing_opportunity_id": (
                        str(existing_opportunity.id)
                        if existing_opportunity is not None
                        else None
                    ),
                    "matched_on": "canonical_url",
                },
            )

        platform_code = detect_platform_code(request.source.url)
        platform = (
            await session.execute(
                select(Platform).where(Platform.code == platform_code)
            )
        ).scalar_one()

        listing = Listing(
            portfolio_id=request.portfolio_id,
            platform_id=platform.id,
            seller_id=seller.id if seller is not None else None,
            watch_id=watch.id,
            canonical_url=canonical_url,
            status="unknown",
        )
        session.add(listing)
        await session.flush()

    opportunity = Opportunity(
        portfolio_id=request.portfolio_id,
        created_by_user_id=principal.user_id,
        source_mode=request.source.mode,
        manual_identifier=(
            request.source.manual_identifier
            if request.source.mode == "manual"
            else None
        ),
        listing_id=listing.id if listing is not None else None,
        watch_id=watch.id,
        seller_id=seller.id if seller is not None else None,
    )
    session.add(opportunity)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise DomainError(
            ErrorCode.OPPORTUNITY_DUPLICATE,
            "Cette opportunité existe déjà dans ce portefeuille.",
        ) from exc

    warnings: list[str] = []
    price_input: OpportunityPriceInput | None = None
    if request.price.amount is not None:
        assert request.price.currency is not None
        fx = await resolve_fx(
            session, request.price.currency, settings.fx_max_age_hours
        )
        if fx is None:
            warnings.append(
                "Prix non enregistré : aucun taux de change récent pour "
                f"{request.price.currency}."
            )
        else:
            price_input = OpportunityPriceInput(
                portfolio_id=request.portfolio_id,
                opportunity_id=opportunity.id,
                kind="asking",
                amount_source=request.price.amount,
                currency=request.price.currency.upper(),
                amount_eur=fx.convert(request.price.amount),
                rate_to_eur=fx.rate_to_eur,
                fx_rate_at=fx.fx_rate_at,
                fx_source=fx.fx_source,
                fx_rate_id=fx.fx_rate_id,
                actor_user_id=principal.user_id,
            )
            session.add(price_input)
            await session.flush()
    elif request.price.missing_reason is not None:
        price_input = OpportunityPriceInput(
            portfolio_id=request.portfolio_id,
            opportunity_id=opportunity.id,
            kind="asking",
            missing_reason=request.price.missing_reason,
            actor_user_id=principal.user_id,
        )
        session.add(price_input)
        await session.flush()

    await session.commit()

    return CreateOpportunityResult(
        opportunity=opportunity,
        watch=watch,
        reference=watch_reference,
        seller=seller,
        price_input=price_input,
        warnings=warnings,
    )
