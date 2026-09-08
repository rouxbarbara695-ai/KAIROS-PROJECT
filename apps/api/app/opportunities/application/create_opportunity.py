from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.opportunities import (
    CreateOpportunityRequest,
    ImportDraftInput,
)
from app.identity.domain import vocabularies as vocab
from app.identity.domain.seller import reliability_data
from app.opportunities.domain.canonical_url import canonicalize_url
from app.platforms.application.detect_platform import detect_platform_code
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.listings import Listing, ListingObservation
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

    # La plateforme d'achat ne se déclare que faute d'annonce : quand il y en a
    # une, c'est elle qui porte la plateforme, et deux sources de vérité
    # finiraient par diverger.
    purchase_platform_id: uuid.UUID | None = None
    if listing is None and request.source.platform_code is not None:
        purchase_platform_id = (
            await session.execute(
                select(Platform.id).where(Platform.code == request.source.platform_code)
            )
        ).scalar_one_or_none()
        if purchase_platform_id is None:
            raise DomainError(
                ErrorCode.NOT_FOUND,
                "Plateforme d'achat inconnue.",
                field="source.platform_code",
            )

    opportunity = Opportunity(
        portfolio_id=request.portfolio_id,
        purchase_platform_id=purchase_platform_id,
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
                # La nature vient de l'appelant. Une enchère Catawiki arrive
                # en `current_bid` : elle montera, et la traiter comme un prix
                # demandé ferait calculer une marge sur un montant qui
                # n'existera peut-être jamais (règle 5).
                kind=request.price.kind,
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
            kind=request.price.kind,
            missing_reason=request.price.missing_reason,
            actor_user_id=principal.user_id,
        )
        session.add(price_input)
        await session.flush()

    if request.import_draft is not None and listing is not None:
        warnings.extend(
            await _record_import(session, request, listing, opportunity.portfolio_id)
        )

    await session.commit()

    return CreateOpportunityResult(
        opportunity=opportunity,
        watch=watch,
        reference=watch_reference,
        seller=seller,
        price_input=price_input,
        warnings=warnings,
    )


_RESERVE_TO_BOOLEAN = {"met": True, "not_met": False}


def _draft_value(draft: ImportDraftInput, name: str) -> object:
    field = draft.fields.get(name)
    if field is None or field.provenance == "absent":
        return None
    return field.value


async def _record_import(
    session: AsyncSession,
    request: CreateOpportunityRequest,
    listing: Listing,
    portfolio_id: uuid.UUID,
) -> list[str]:
    """Conserve ce que l'annonce affichait, tel qu'elle l'affichait.

    Écrit dans `listing_observations`, qui est **append-only** : c'est un
    constat daté, pas un état à tenir à jour. Rouvrir le dossier six semaines
    plus tard doit permettre de dire « ce 3 250 € venait de l'annonce, ce
    « Or/acier » a été corrigé à la main » — et une seconde récupération
    ajoutera une observation plutôt que d'écraser celle-ci.

    La page elle-même n'est pas conservée (Q-08) : seulement les champs
    extraits, leur valeur brute et leur provenance.
    """

    draft = request.import_draft
    assert draft is not None
    warnings: list[str] = []

    closing_raw = _draft_value(draft, "closing_at")
    closing_at: datetime | None = None
    if isinstance(closing_raw, str):
        try:
            closing_at = datetime.fromisoformat(closing_raw)
        except ValueError:  # pragma: no cover - l'extracteur produit de l'ISO
            closing_at = None

    reserve = _draft_value(draft, "reserve_status")
    observed_at: datetime
    try:
        observed_at = datetime.fromisoformat(draft.fetched_at)
    except ValueError:
        observed_at = datetime.now(UTC)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)

    observation = ListingObservation(
        portfolio_id=portfolio_id,
        listing_id=listing.id,
        observed_at=observed_at,
        # `unknown` et non `active` : l'import dit ce que la page affichait,
        # pas si le lot est encore ouvert au moment de l'enregistrement.
        status="unknown",
        reserve_met=(
            _RESERVE_TO_BOOLEAN.get(str(reserve)) if reserve is not None else None
        ),
        auction_end_at=closing_at,
        raw_data={
            "platform_code": draft.platform_code,
            "access_mode": draft.access_mode,
            "fetched_at": draft.fetched_at,
            "warnings": list(draft.warnings),
            "fields": {
                name: field.model_dump() for name, field in draft.fields.items()
            },
        },
        # `partial` est le cas honnête : une annonce donne rarement tous les
        # champs, et l'appeler `success` ferait croire à une fiche complète.
        fetch_status="partial",
    )
    session.add(observation)
    await session.flush()

    if closing_at is None and _draft_value(draft, "current_bid_amount") is not None:
        warnings.append(
            "Enchère en cours enregistrée sans date de clôture : la surveiller "
            "sur Catawiki."
        )

    return warnings
