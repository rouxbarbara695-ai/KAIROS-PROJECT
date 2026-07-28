from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.api.v1.schemas.common import DecimalString


class SourceCreate(BaseModel):
    mode: Literal["manual", "url"]
    manual_identifier: str | None = None
    url: str | None = None

    @model_validator(mode="after")
    def _check_required_field(self) -> SourceCreate:
        if self.mode == "manual" and not self.manual_identifier:
            raise ValueError("manual_identifier est requis en mode manuel.")
        if self.mode == "url" and not self.url:
            raise ValueError("url est requise en mode url.")
        return self


class WatchCreate(BaseModel):
    brand: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    reference_status: Literal["unconfirmed", "unknown"] = "unconfirmed"
    mechanical_condition: str | None = None
    cosmetic_condition: str | None = None
    box: bool | None = None
    papers: bool | None = None
    originality: str | None = None


class SellerCreate(BaseModel):
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    seller_type: str | None = None


class PriceCreate(BaseModel):
    amount: DecimalString | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    missing_reason: str | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> PriceCreate:
        if self.amount is not None and self.currency is None:
            raise ValueError("currency est requis dès qu'un montant est fourni.")
        if self.amount is None and self.missing_reason is None:
            self.missing_reason = "asking_price_not_provided"
        return self


class CreateOpportunityRequest(BaseModel):
    portfolio_id: uuid.UUID
    source: SourceCreate
    watch: WatchCreate
    seller: SellerCreate = SellerCreate()
    price: PriceCreate = PriceCreate()


class OpportunityResponse(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    source_mode: str
    manual_identifier: str | None
    status: str
    version: int
    watch: WatchProfileResponse
    seller: SellerProfileResponse | None
    latest_price: PriceResponse | None
    latest_analysis: None = None
    created_at: datetime
    updated_at: datetime


class WatchProfileResponse(BaseModel):
    id: uuid.UUID
    reference_id: uuid.UUID | None
    brand: str | None
    reference: str | None
    reference_status: str
    identification_confidence: DecimalString | None
    condition_data: dict[str, object]
    completeness_data: dict[str, object]


class SellerProfileResponse(BaseModel):
    id: uuid.UUID
    country_code: str | None
    seller_type: str | None


class PriceResponse(BaseModel):
    amount: DecimalString | None
    currency: str | None
    amount_eur: DecimalString | None
    missing_reason: str | None
    observed_at: datetime


class ReferenceConfirmationRequest(BaseModel):
    status: Literal["suggested", "confirmed", "corrected", "unknown"]
    reference_id: uuid.UUID | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_reference_id(self) -> ReferenceConfirmationRequest:
        if self.status in ("confirmed", "corrected") and self.reference_id is None:
            raise ValueError(
                "reference_id est requis pour un statut confirmed/corrected."
            )
        return self


class WatchProfilePatchRequest(BaseModel):
    mechanical_condition: str | None = None
    cosmetic_condition: str | None = None
    box: bool | None = None
    papers: bool | None = None
    originality: str | None = None
    reason: str = Field(min_length=1)


class SellerProfilePatchRequest(BaseModel):
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    seller_type: str | None = None
    reason: str = Field(min_length=1)


class OpportunityPatchRequest(BaseModel):
    strategy_id: uuid.UUID | None = None
    reason: str = Field(min_length=1)


class PriceInputCreate(BaseModel):
    kind: Literal["asking", "offer", "accepted_offer", "current_bid", "hammer"]
    amount: DecimalString | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    missing_reason: str | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> PriceInputCreate:
        if self.amount is not None and self.currency is None:
            raise ValueError("currency est requis dès qu'un montant est fourni.")
        if self.amount is None and self.missing_reason is None:
            raise ValueError("missing_reason est requis quand amount est absent.")
        return self


class PageMeta(BaseModel):
    next_cursor: str | None


class OpportunityPage(BaseModel):
    items: list[OpportunityResponse]
    next_cursor: str | None


# Résolution du forward-ref (WatchProfileResponse/SellerProfileResponse
# définis après OpportunityResponse ci-dessus).
OpportunityResponse.model_rebuild()
