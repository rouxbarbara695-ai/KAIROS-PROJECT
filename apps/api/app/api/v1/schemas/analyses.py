from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.api.v1.schemas.common import DecimalString


class GateResultResponse(BaseModel):
    code: str
    status: str
    reason_codes: list[str]
    blocking: bool


class AnalysisResponse(BaseModel):
    """Analyse figée et sa trace complète.

    Tous les nombres sont des chaînes décimales : un score, un ROI ou un prix
    qui transiterait en flottant perdrait la valeur exacte qui a été calculée
    et figée (api-contract.md, CLAUDE.md règle 2).

    `explanation`, `pillars`, `caps` et `scenario_results` portent les entrées,
    règles, versions, exclusions, plafonds et motifs qu'exige la règle 6 :
    une recommandation doit pouvoir être rejouée et contestée.
    """

    id: uuid.UUID
    opportunity_id: uuid.UUID
    calculated_at: datetime
    state: str
    recommendation: str

    current_price_eur: DecimalString | None = None
    total_cost_eur: DecimalString | None = None
    expected_sale_price_eur: DecimalString | None = None
    max_purchase_price_eur: DecimalString | None = None
    raw_max_purchase_price_eur: DecimalString | None = None
    expected_profit_eur: DecimalString | None = None
    expected_roi: DecimalString | None = None
    expected_days_to_sell: int | None = None
    score: DecimalString | None = None
    evidence_quality_score: DecimalString | None = None

    gates: list[GateResultResponse]
    pillars: dict[str, object] | None = None
    scenario_results: dict[str, object] | None = None
    caps: list[dict[str, object]]
    explanation: dict[str, object]
    strategy_snapshot: dict[str, object] | None = None
    portfolio_snapshot: dict[str, object] | None = None

    # `ruleset_snapshot` n'est volontairement pas exposé : il pèse près d'un
    # mégaoctet et n'a d'intérêt qu'au rejeu. Sa version figure dans
    # `explanation.ruleset_version`, ce qui suffit à identifier le barème.
