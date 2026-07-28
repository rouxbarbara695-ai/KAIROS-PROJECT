from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.api.v1.schemas.common import DecimalString

PriceKind = Literal[
    "asking",
    "offer",
    "accepted_offer",
    "current_bid",
    "hammer",
    "realized",
    "external_estimate",
    "kairos_estimate",
]
MarketStatus = Literal["active", "sold", "removed", "ended", "unknown"]
ReliabilityClass = Literal["a", "b", "c", "d", "e"]


class ComparableCreate(BaseModel):
    """Comparable saisi manuellement.

    `price_kind` décrit la nature économique du prix, `source_reliability` la
    qualité de la preuve : les deux sont obligatoires et ne se substituent pas
    l'un à l'autre (calculation-spec.md § 2).
    """

    source_name: str = Field(min_length=1)
    source_external_id: str | None = None
    seller_fingerprint: str | None = None

    price_kind: PriceKind
    amount: DecimalString
    currency: str = Field(min_length=3, max_length=3)

    buyer_variable_fee_eur: DecimalString | None = None
    buyer_fixed_fee_eur: DecimalString | None = None
    compulsory_shipping_eur: DecimalString | None = None

    market_status: MarketStatus
    listed_at: datetime | None = None
    ended_at: datetime | None = None
    observed_at: datetime

    source_reliability: ReliabilityClass

    mechanical_condition: str | None = None
    cosmetic_condition: str | None = None
    box: bool | None = None
    papers: bool | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> ComparableCreate:
        if (
            self.listed_at is not None
            and self.ended_at is not None
            and self.ended_at < self.listed_at
        ):
            raise ValueError("ended_at ne peut pas précéder listed_at.")
        return self


class ComparableResponse(BaseModel):
    id: uuid.UUID
    source_name: str
    price_kind: str
    amount_source: DecimalString
    currency: str
    amount_eur: DecimalString
    rate_to_eur: DecimalString
    fx_source: str
    fx_rate_at: datetime
    buyer_total_price_eur: DecimalString
    market_status: str
    observed_at: datetime
    listed_at: datetime | None
    ended_at: datetime | None
    source_reliability: str
    condition_data: dict[str, object]
    completeness_data: dict[str, object]
    excluded: bool
    exclusion_reason: str | None


class ComparablePage(BaseModel):
    items: list[ComparableResponse]
    next_cursor: str | None


class OverrideCreate(BaseModel):
    """Correction, exclusion ou réintégration d'un comparable.

    Une exclusion exige son propre motif en plus du motif d'audit : le premier
    documente la décision métier, le second la trace (schéma `comparable_overrides`).
    """

    excluded: bool
    exclusion_reason: str | None = None
    corrected_data: dict[str, object] = Field(default_factory=dict)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_exclusion_reason(self) -> OverrideCreate:
        if self.excluded and not (self.exclusion_reason or "").strip():
            raise ValueError("exclusion_reason est requis pour exclure un comparable.")
        return self


class OverrideResponse(BaseModel):
    id: uuid.UUID
    comparable_id: uuid.UUID
    previous_override_id: uuid.UUID | None
    excluded: bool
    exclusion_reason: str | None
    corrected_data: dict[str, object]
    reason: str
    created_at: datetime


class ComparableImportRow(BaseModel):
    line: int
    error: str


class ComparableImportResult(BaseModel):
    """Résultat d'un import CSV.

    Les lignes valides sont importées et les lignes en échec rapportées avec
    leur numéro : un fichier partiellement erroné ne fait pas perdre le travail
    de saisie déjà correct.
    """

    imported: int
    rejected: list[ComparableImportRow]


class ValuationResponse(BaseModel):
    """Cote figée et sa trace.

    `explanation` porte les entrées, exclusions, plafonds et versions exigés
    par la règle 6 : une cote doit pouvoir être rejouée et contestée.
    """

    id: uuid.UUID
    opportunity_id: uuid.UUID
    calculated_at: datetime
    low_value_eur: DecimalString
    central_value_eur: DecimalString
    high_value_eur: DecimalString
    valuation_confidence: DecimalString
    explanation: dict[str, object]


class ComparableImportRequest(BaseModel):
    """Contenu CSV lu côté client. Éviter le multipart garde l'API homogène et
    testable sans dépendance supplémentaire."""

    content: str = Field(min_length=1)
