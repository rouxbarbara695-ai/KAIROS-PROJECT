from __future__ import annotations

from app.api.v1.schemas.opportunities import (
    OpportunityResponse,
    PriceResponse,
    SellerProfileResponse,
    WatchProfileResponse,
)
from app.identity.domain.seller import PROTECTIONS, RELIABILITY, RISK_LEVEL
from app.shared.infrastructure.db.models.opportunities import (
    Opportunity,
    OpportunityPriceInput,
)
from app.shared.infrastructure.db.models.watches import Seller, Watch, WatchReference


def _seller_field(seller: Seller, key: str) -> str | None:
    """`None` quand le champ n'a jamais été renseigné, ce qui se distingue de
    « inconnu » : l'un est une case vide du formulaire, l'autre un constat."""

    value = seller.reliability_data.get(key)
    return str(value) if value is not None else None


def to_opportunity_response(
    opportunity: Opportunity,
    watch: Watch,
    reference: WatchReference | None,
    seller: Seller | None,
    latest_price: OpportunityPriceInput | None,
    purchase_platform_code: str | None = None,
) -> OpportunityResponse:
    return OpportunityResponse(
        id=opportunity.id,
        portfolio_id=opportunity.portfolio_id,
        source_mode=opportunity.source_mode,
        manual_identifier=opportunity.manual_identifier,
        purchase_platform_code=purchase_platform_code,
        status=opportunity.status,
        version=opportunity.version,
        watch=WatchProfileResponse(
            id=watch.id,
            reference_id=watch.reference_id,
            brand=reference.brand if reference is not None else None,
            reference=reference.reference if reference is not None else None,
            reference_status=watch.reference_status,
            identification_confidence=watch.identification_confidence,
            condition_data=watch.condition_data,
            completeness_data=watch.completeness_data,
        ),
        seller=(
            SellerProfileResponse(
                id=seller.id,
                country_code=seller.country_code,
                seller_type=seller.seller_type,
                reliability=_seller_field(seller, RELIABILITY),
                risk_level=_seller_field(seller, RISK_LEVEL),
                transaction_protections=_seller_field(seller, PROTECTIONS),
            )
            if seller is not None
            else None
        ),
        latest_price=(
            PriceResponse(
                amount=latest_price.amount_source,
                currency=latest_price.currency,
                amount_eur=latest_price.amount_eur,
                missing_reason=latest_price.missing_reason,
                observed_at=latest_price.observed_at,
            )
            if latest_price is not None
            else None
        ),
        created_at=opportunity.created_at,
        updated_at=opportunity.updated_at,
    )
