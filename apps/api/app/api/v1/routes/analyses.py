from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.analyses import AnalysisResponse, GateResultResponse
from app.scoring.application.run_analysis import run_analysis
from app.shared.config import Settings, get_settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.analyses import Analysis
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.principal_provider import get_current_principal

router = APIRouter(tags=["analyses"])


def _gate(raw: object) -> GateResultResponse:
    """La colonne est du JSONB : son contenu n'est typé que par ce qui l'a
    écrit. Le valider ici plutôt que de le supposer évite de servir une
    analyse silencieusement malformée."""

    if not isinstance(raw, dict):
        raise DomainError(
            ErrorCode.VALIDATION_ERROR, "Porte mal formée dans l'analyse figée."
        )
    return GateResultResponse.model_validate(raw)


def _caps(raw: list[object]) -> list[dict[str, object]]:
    return [item for item in raw if isinstance(item, dict)]


def _to_response(analysis: Analysis) -> AnalysisResponse:
    return AnalysisResponse(
        id=analysis.id,
        opportunity_id=analysis.opportunity_id,
        calculated_at=analysis.calculated_at,
        state=analysis.state,
        recommendation=analysis.recommendation,
        current_price_eur=analysis.current_price_eur,
        total_cost_eur=analysis.total_cost_eur,
        expected_sale_price_eur=analysis.expected_sale_price_eur,
        max_purchase_price_eur=analysis.max_purchase_price_eur,
        raw_max_purchase_price_eur=analysis.raw_max_purchase_price_eur,
        expected_profit_eur=analysis.expected_profit_eur,
        expected_roi=analysis.expected_roi,
        expected_days_to_sell=analysis.expected_days_to_sell,
        score=analysis.score,
        evidence_quality_score=analysis.evidence_quality_score,
        gates=[_gate(gate) for gate in analysis.gates],
        pillars=analysis.pillars,
        scenario_results=analysis.scenario_results,
        caps=_caps(analysis.caps),
        explanation=analysis.explanation,
        strategy_snapshot=analysis.strategy_snapshot,
        portfolio_snapshot=analysis.portfolio_snapshot,
    )


@router.post(
    "/opportunities/{opportunity_id}/analyses",
    status_code=status.HTTP_201_CREATED,
    response_model=AnalysisResponse,
)
async def create_analysis_route(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> AnalysisResponse:
    """Recalcule l'analyse. Chaque appel crée une version chaînée à la
    précédente : une analyse n'est jamais écrasée (CLAUDE.md règle 4)."""

    analysis = await run_analysis(session, principal, opportunity_id, settings)
    return _to_response(analysis)


@router.get(
    "/opportunities/{opportunity_id}/analyses/latest",
    response_model=AnalysisResponse,
)
async def get_latest_analysis_route(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> AnalysisResponse:
    analysis = (
        await session.execute(
            select(Analysis)
            .join(Opportunity, Opportunity.id == Analysis.opportunity_id)
            .where(
                Analysis.opportunity_id == opportunity_id,
                # Filtrer par portefeuille ici aussi : une analyse d'un autre
                # portefeuille doit être indiscernable d'une analyse
                # inexistante, sans fuite d'existence.
                Opportunity.portfolio_id.in_(principal.portfolio_ids),
            )
            .order_by(Analysis.calculated_at.desc(), Analysis.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if analysis is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Aucune analyse pour cette opportunité.")

    return _to_response(analysis)
