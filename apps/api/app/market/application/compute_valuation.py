from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import cast, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.application.list_comparables import ComparableView
from app.market.domain.comparable import (
    WeightFactors,
    adjust_for_set,
    comparable_weight,
    completeness_gap,
    condition_gap,
)
from app.market.domain.confidence import ConfidenceInput, valuation_confidence
from app.market.domain.valuation import (
    WeightedPrice,
    detect_outliers,
    market_quote,
)
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.market import (
    Comparable,
    MarketValuation,
    ValuationComparable,
)
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.reference_data import Ruleset as RulesetRow
from app.shared.infrastructure.db.models.watches import Watch
from app.shared.infrastructure.ruleset_loader import load_ruleset
from app.shared.rules.ruleset import Ruleset

_SET_PREMIUM = ("comparable", "set_premium")


@dataclass(slots=True)
class _Assessed:
    """Un comparable et tout ce que le calcul en a tiré, prêt à être figé.

    `anomaly` est renseigné dans un second temps : la détection porte sur
    l'ensemble des prix ajustés et ne peut donc pas être connue comparable
    par comparable.
    """

    comparable: Comparable
    adjusted_price_eur: Decimal
    comparable_premium: Decimal
    target_premium: Decimal
    factors: WeightFactors
    anomaly: bool
    excluded: bool
    exclusion_reason: str | None


def _age_days(observed_at: datetime, now: datetime) -> int:
    delta = now - observed_at
    return max(delta.days, 0)


async def compute_valuation(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    settings: Settings,
    views: list[ComparableView],
) -> MarketValuation:
    """Calcule une cote et la fige, avec sa trace complète.

    Une valorisation est immuable : un recalcul crée une nouvelle version
    plutôt que d'écraser la précédente (CLAUDE.md règle 4). Chaque comparable
    retenu est figé avec l'intégralité de ses facteurs, de sorte que la cote
    reste rejouable même si le comparable évolue ensuite.
    """

    opportunity = (
        await session.execute(
            select(Opportunity).where(
                Opportunity.id == opportunity_id,
                Opportunity.portfolio_id.in_(principal.portfolio_ids),
            )
        )
    ).scalar_one_or_none()
    if opportunity is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Opportunité introuvable.")

    watch = (
        await session.execute(select(Watch).where(Watch.id == opportunity.watch_id))
    ).scalar_one()

    ruleset = await load_ruleset(session, settings.active_ruleset_version)
    ruleset_id = await _ruleset_id(session, settings.active_ruleset_version)

    now = datetime.now(UTC)
    target_level = str(watch.completeness_data.get("level", "watch_only"))

    assessed = _assess(views, watch, target_level, ruleset, now)

    # Les comparables écartés par décision humaine ne participent ni au calcul
    # ni à la détection d'anomalies : une exclusion motivée ne doit pas
    # influencer indirectement le seuil qui exclut les autres.
    retained = [item for item in assessed if not item.excluded]

    report = detect_outliers([item.adjusted_price_eur for item in retained], ruleset)
    for index, item in enumerate(retained):
        item.anomaly = report.flagged[index]

    usable = [item for item in retained if not item.anomaly]

    quote = market_quote(
        [
            WeightedPrice(
                adjusted_price_eur=item.adjusted_price_eur,
                weight=item.factors.weight,
            )
            for item in usable
        ],
        ruleset,
    )

    confidence = valuation_confidence(
        [
            ConfidenceInput(
                reliability_class=item.comparable.source_reliability,
                recency_factor=item.factors.recency,
                reference_similarity=item.factors.reference_similarity,
                condition_similarity=item.factors.condition_similarity,
                completeness_similarity=item.factors.completeness_similarity,
                seller_key=item.comparable.seller_fingerprint
                or str(item.comparable.id),
            )
            for item in usable
        ],
        quote,
        identity_confirmed=watch.reference_status in ("confirmed", "corrected"),
        ruleset=ruleset,
    )

    valuation = MarketValuation(
        portfolio_id=opportunity.portfolio_id,
        opportunity_id=opportunity.id,
        ruleset_id=ruleset_id,
        low_value_eur=quote.low_eur,
        central_value_eur=quote.central_eur,
        high_value_eur=quote.high_eur,
        valuation_confidence=confidence.value,
        # Figé depuis le texte source : le barème conservé reste exactement
        # celui qui a produit la cote, décimales comprises.
        ruleset_snapshot=cast(literal(ruleset.raw_config), JSONB),
        explanation={
            "ruleset_version": ruleset.version,
            "target_completeness": target_level,
            "identity_confirmed": watch.reference_status in ("confirmed", "corrected"),
            "comparables_total": len(assessed),
            "comparables_excluded_by_user": sum(1 for i in assessed if i.excluded),
            "comparables_flagged_as_anomaly": report.flagged_count,
            "comparables_used": len(usable),
            "outlier_method": report.method,
            "widened_for_small_sample": quote.widened_for_small_sample,
            "confidence": {
                "value": str(confidence.value),
                "uncapped_value": str(confidence.uncapped_value),
                "volume": str(confidence.volume_score),
                "source_reliability": str(confidence.source_reliability_score),
                "recency": str(confidence.recency_score),
                "similarity": str(confidence.similarity_score),
                "dispersion": str(confidence.dispersion_score),
                "applied_caps": [
                    {"name": cap.name, "value": str(cap.value), "reason": cap.reason}
                    for cap in confidence.applied_caps
                ],
            },
        },
    )
    session.add(valuation)
    await session.flush()

    for item in assessed:
        session.add(
            ValuationComparable(
                valuation_id=valuation.id,
                comparable_id=item.comparable.id,
                source_amount_snapshot=item.comparable.amount_source,
                source_currency_snapshot=item.comparable.currency,
                amount_eur_snapshot=item.comparable.amount_eur,
                buyer_total_price_eur=item.comparable.buyer_total_price_eur,
                comparable_set_premium=item.comparable_premium,
                target_set_premium=item.target_premium,
                adjusted_price_eur=item.adjusted_price_eur,
                source_reliability_factor=item.factors.source_reliability,
                recency_factor=item.factors.recency,
                reference_factor=item.factors.reference_similarity,
                condition_factor=item.factors.condition_similarity,
                completeness_factor=item.factors.completeness_similarity,
                seller_independence_factor=item.factors.seller_independence,
                final_weight=item.factors.weight,
                anomaly_flag=item.anomaly,
                excluded=item.excluded or item.anomaly,
                exclusion_reason=item.exclusion_reason
                or ("anomalie statistique" if item.anomaly else None),
            )
        )

    await session.commit()
    await session.refresh(valuation)
    return valuation


async def _ruleset_id(session: AsyncSession, version: str) -> uuid.UUID:
    row = (
        await session.execute(
            select(RulesetRow.id).where(RulesetRow.version == version)
        )
    ).scalar_one_or_none()
    if row is None:
        raise DomainError(
            ErrorCode.RULESET_MISSING,
            f"Ruleset {version} introuvable.",
            details={"ruleset_version": version},
        )
    return row


def _assess(
    views: list[ComparableView],
    watch: Watch,
    target_level: str,
    ruleset: Ruleset,
    now: datetime,
) -> list[_Assessed]:
    seen_sellers: dict[str, int] = {}
    for view in views:
        key = view.comparable.seller_fingerprint
        if key:
            seen_sellers[key] = seen_sellers.get(key, 0) + 1

    assessed: list[_Assessed] = []
    for view in views:
        comparable = view.comparable
        level = str(comparable.completeness_data.get("level", "watch_only"))

        adjusted = adjust_for_set(
            comparable.buyer_total_price_eur, level, target_level, ruleset
        )

        fingerprint = comparable.seller_fingerprint
        relation = (
            "probable_duplicate"
            if fingerprint and seen_sellers.get(fingerprint, 0) > 1
            else "independent"
        )

        factors = comparable_weight(
            reliability_class=comparable.source_reliability,
            age_days=_age_days(comparable.observed_at, now),
            # Les comparables sont rattachés à la même référence que la montre :
            # la similarité de référence est exacte par construction.
            reference_match="same",
            condition_gap=condition_gap(
                comparable.condition_data, watch.condition_data
            ),
            completeness_gap=completeness_gap(level, target_level),
            seller_relation=relation,
            ruleset=ruleset,
        )

        assessed.append(
            _Assessed(
                comparable=comparable,
                adjusted_price_eur=adjusted,
                comparable_premium=ruleset.decimal_in(_SET_PREMIUM, level),
                target_premium=ruleset.decimal_in(_SET_PREMIUM, target_level),
                factors=factors,
                anomaly=False,
                excluded=view.excluded,
                exclusion_reason=view.exclusion_reason,
            )
        )

    return assessed
