from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.v1.schemas.comparables import RecalculationResponse

SourceStatus = Literal[
    "ok",
    "not_configured",
    "blocked",
    "rate_limited",
    "budget_exhausted",
    "error",
]
RunStatus = Literal["queued", "running", "succeeded", "failed", "partial"]


class MarketSearchStartRequest(BaseModel):
    """`force` demande une actualisation avant l'expiration de la fraîcheur.

    Elle reste refusée (résultat précédent renvoyé) si la dernière recherche date
    de moins de quelques minutes : chaque requête coûte du quota à la source.
    """

    force: bool = False


class SourceRequestRecord(BaseModel):
    label: str
    http_status: int | None
    elapsed_s: float
    note: str | None = None


class RejectedExample(BaseModel):
    title: str
    code: str
    detail: str


class RecordedItem(BaseModel):
    comparable_id: uuid.UUID
    title: str
    url: str
    amount: str
    currency: str
    price_kind: str


class SourceResult(BaseModel):
    """Ce qu'une source a réellement fait : requêtes, lectures, retenues, écartées.

    Un échec est un statut, avec son diagnostic exact — jamais une liste vide qui
    se ferait passer pour « aucune annonce ».
    """

    source: str
    status: SourceStatus
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_s: float = 0.0
    requests: list[SourceRequestRecord] = Field(default_factory=list)
    requests_count: int = 0
    read: int = 0
    accepted: int = 0
    recorded: int = 0
    already_known: int = 0
    duplicates: int = 0
    fx_unavailable: int = 0
    rejected: dict[str, int] = Field(default_factory=dict)
    rejected_examples: list[RejectedExample] = Field(default_factory=list)
    recorded_items: list[RecordedItem] = Field(default_factory=list)


class SearchSummary(BaseModel):
    stage: Literal["queued", "searching", "recalculating", "done"] = "queued"
    elapsed_s: float | None = None
    observed_at: datetime | None = None
    comparables_recorded: int = 0
    comparables_known_for_reference: int | None = None
    recorded_by_price_kind: dict[str, int] = Field(default_factory=dict)
    insufficient_data: bool = False
    insufficient_data_message: str | None = None
    price_nature_note: str | None = None
    recalculation: RecalculationResponse | None = None


class MarketSearchRunResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    status: RunStatus
    trigger_kind: Literal["reference_confirmed", "refresh"]
    policy_version: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    sources: list[SourceResult]
    summary: SearchSummary
    error_code: str | None = None
    error_message: str | None = None
    # Fraîcheur : l'âge des données affichées est toujours dit (les conditions de
    # l'API eBay l'exigent au-delà de six heures).
    age_minutes: int | None = None
    stale: bool = False
    cache_ttl_hours: int
    next_refresh_allowed_at: datetime | None = None


class MarketSearchStartResponse(MarketSearchRunResponse):
    #: `True` si une nouvelle recherche vient d'être lancée.
    launched: bool
    #: `running`, `fresh` ou `too_soon` quand la demande est ramenée à une
    #: recherche existante.
    reused: Literal["running", "fresh", "too_soon"] | None = None


class MarketSearchLatestResponse(BaseModel):
    run: MarketSearchRunResponse | None
    #: Sources qui peuvent être interrogées. Vide : la recherche automatique est
    #: indisponible, et l'écran doit le dire au lieu de laisser un bouton inerte.
    configured_sources: list[str]
