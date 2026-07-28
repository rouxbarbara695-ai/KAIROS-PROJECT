from __future__ import annotations

from app.api.v1.schemas.opportunities import (
    OpportunityResponse,
    PriceResponse,
    SellerProfileResponse,
    WatchProfileResponse,
)
from app.shared.infrastructure.db.models.opportunities import (
    Opportunity,
    OpportunityPriceInput,
)
from app.shared.infrastructure.db.models.watches import Seller, Watch, WatchReference


def to_opportunity_response(
    opportunity: Opportunity,
    watch: Watch,
    reference: WatchReference | None,
    seller: Seller | None,
    latest_price: OpportunityPriceInput | None,
) -> OpportunityResponse:
    return OpportunityResponse(
        id=opportunity.id,
        portfolio_id=opportunity.portfolio_id,
        source_mode=opportunity.source_mode,
        manual_identifier=opportunity.manual_identifier,
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
