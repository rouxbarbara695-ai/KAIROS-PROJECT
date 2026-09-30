from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api.v1.schemas.market_search import (
    MarketSearchRunResponse,
    SearchSummary,
    SourceResult,
)
from app.market_search.domain.policy import SearchPolicy
from app.shared.infrastructure.db.models.jobs import MarketSearchRun


def to_run_response(
    run: MarketSearchRun, policy: SearchPolicy, now: datetime | None = None
) -> MarketSearchRunResponse:
    now = now or datetime.now(UTC)
    age_minutes: int | None = None
    stale = False
    next_refresh: datetime | None = None
    if run.finished_at is not None:
        age = now - run.finished_at
        age_minutes = max(int(age.total_seconds() // 60), 0)
        stale = age > timedelta(hours=policy.cache_ttl_hours)
        next_refresh = run.finished_at + timedelta(minutes=policy.min_refresh_minutes)

    return MarketSearchRunResponse(
        id=run.id,
        opportunity_id=run.opportunity_id,
        status=run.status,
        trigger_kind=run.trigger_kind,
        policy_version=run.policy_version,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        sources=[SourceResult.model_validate(entry) for entry in run.sources],
        summary=SearchSummary.model_validate(run.summary),
        error_code=run.error_code,
        error_message=run.error_message,
        age_minutes=age_minutes,
        stale=stale,
        cache_ttl_hours=policy.cache_ttl_hours,
        next_refresh_allowed_at=next_refresh,
    )
