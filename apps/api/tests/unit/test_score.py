from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.scoring.domain.curves import curve, interpolate
from app.scoring.domain.gates import GateInputs, evaluate_gates
from app.scoring.domain.score import (
    ScoreInputs,
    Verdict,
    compute_score,
    most_cautious,
)
from app.shared.rules.ruleset import Ruleset

_SEED = Path(__file__).parents[4] / "database" / "schema.sql"


@pytest.fixture(scope="module")
def ruleset() -> Ruleset:
    sql = _SEED.read_text(encoding="utf-8")
    start = sql.index("'{", sql.index("with seed(version, config, valid_from)")) + 1
    end = sql.index("'::jsonb", start)
    return Ruleset(
        version="1.0.0", config=json.loads(sql[start:end], parse_float=Decimal)
    )


def _gates(**overrides: object):
    base: dict = {
        "reference_status": "confirmed",
        "identification_confidence": Decimal("95"),
        "has_price": True,
        "has_currency": True,
        "has_condition": True,
        "has_completeness": True,
        "has_seller_country": True,
        "comparable_count": 8,
        "total_weight": Decimal("6"),
        "authenticity_signals": (),
        "seller_risk_level": "low",
    }
    base.update(overrides)
    return GateInputs(**base)  # type: ignore[arg-type]


def _inputs(**overrides: object) -> ScoreInputs:
    base: dict = {
        "central_profit_eur": Decimal("500"),
        "central_roi": Decimal("0.20"),
        "sale_delay_days": 14,
        "active_comparable_depth": 20,
        "dispersion_subscore": Decimal("100"),
        "allocation_rate": Decimal("0.10"),
        "brand_concentration_rate": Decimal("0.10"),
        "capital_immobilization_rate": Decimal("0.10"),
        "maximum_allocation_rate": Decimal("0.50"),
        "mechanical": "verified",
        "cosmetic": "excellent",
        "completeness": "full_set",
        "originality": "original",
        "listing_quality_score": Decimal("100"),
        "valuation_confidence": Decimal("100"),
        "seller_reliability": "verified",
        "transaction_protections": "authentication_and_escrow",
    }
    base.update(overrides)
    return ScoreInputs(**base)  # type: ignore[arg-type]


def _score(ruleset: Ruleset, gate_overrides=None, **overrides):
    gates = evaluate_gates(_gates(**(gate_overrides or {})), ruleset)
    return compute_score(_inputs(**overrides), gates, ruleset)


# --- Interpolation -------------------------------------------------------


def test_interpolation_is_linear_between_points(ruleset: Ruleset) -> None:
    points = curve(ruleset, "profit_eur")
    # 150 € est à mi-chemin entre 100 € (25) et 200 € (50).
    assert interpolate(points, Decimal("150")) == Decimal("37.5000")


def test_interpolation_is_bounded_at_both_ends(ruleset: Ruleset) -> None:
    points = curve(ruleset, "profit_eur")
    assert interpolate(points, Decimal("-1000")) == Decimal("0.0000")
    assert interpolate(points, Decimal("100000")) == Decimal("100.0000")


def test_decreasing_curves_are_handled(ruleset: Ruleset) -> None:
    """Le délai décroît quand la valeur augmente : l'orientation appartient à
    la donnée, pas au moteur."""

    points = curve(ruleset, "delay_days")
    assert interpolate(points, Decimal("14")) == Decimal("100.0000")
    assert interpolate(points, Decimal("90")) == Decimal("40.0000")
    assert interpolate(points, Decimal("400")) == Decimal("0.0000")


# --- Score nominal -------------------------------------------------------


def test_a_perfect_file_scores_one_hundred_and_buys(ruleset: Ruleset) -> None:
    result = _score(ruleset)
    assert result.raw_score == Decimal("100.00")
    assert result.final_score == Decimal("100.00")
    assert result.verdict is Verdict.BUY
    assert result.applied_caps == ()
    assert result.blocking_conditions == ()


def test_pillars_are_weighted_as_specified(ruleset: Ruleset) -> None:
    result = _score(
        ruleset,
        mechanical="defect",
        cosmetic="poor",
        originality="major_modification",
        completeness="watch_only",
    )
    # État = 10×0.40 + 10×0.35 + 40×0.20 + 0×0.05 = 15.5
    assert result.condition == Decimal("15.5000")
    # Les autres piliers restent à 100 : 100 − 0.15 × (100 − 15.5) = 87.325,
    # arrondi au demi supérieur à l'exposition — jamais au pair le plus proche.
    assert result.raw_score == Decimal("87.33")


def test_scores_are_not_rounded_before_the_total(ruleset: Ruleset) -> None:
    """Arrondir chaque sous-score au centième avant de sommer déplacerait le
    total ; la spec impose de n'arrondir qu'à l'exposition."""

    result = _score(
        ruleset, central_profit_eur=Decimal("133"), central_roi=Decimal("0.037")
    )
    assert result.subscores["profit"].as_tuple().exponent == -4


# --- Règles de dépendance ------------------------------------------------


def test_negative_profit_zeroes_profitability_and_forces_pass(
    ruleset: Ruleset,
) -> None:
    result = _score(ruleset, central_profit_eur=Decimal("-50"))
    assert result.profitability == Decimal("0")
    assert result.verdict is Verdict.PASS
    assert "central_profit_negative" in result.blocking_conditions


def test_low_confidence_caps_the_score_at_fifty_nine(ruleset: Ruleset) -> None:
    result = _score(ruleset, valuation_confidence=Decimal("30"))
    assert result.final_score == Decimal("59.00")
    assert "valuation_below_40" in [cap.name for cap in result.applied_caps]


def test_medium_confidence_caps_the_score_at_seventy_four(
    ruleset: Ruleset,
) -> None:
    result = _score(ruleset, valuation_confidence=Decimal("50"))
    assert result.final_score == Decimal("74.00")


def test_confidence_below_buy_minimum_prevents_buy(ruleset: Ruleset) -> None:
    result = _score(ruleset, valuation_confidence=Decimal("55"))
    assert result.verdict is not Verdict.BUY
    assert "valuation_confidence_below_buy_minimum" in result.blocking_conditions


def test_allocation_beyond_maximum_caps_the_score(ruleset: Ruleset) -> None:
    result = _score(
        ruleset,
        allocation_rate=Decimal("0.60"),
        maximum_allocation_rate=Decimal("0.50"),
    )
    assert result.final_score <= Decimal("54.00")
    assert "allocation_exceeded" in [cap.name for cap in result.applied_caps]


def test_illiquidity_caps_diversification_before_the_pillar(
    ruleset: Ruleset,
) -> None:
    """Un portefeuille bien réparti mais illiquide ne doit pas paraître sain :
    le plafond s'applique au sous-score, avant le calcul du pilier."""

    result = _score(
        ruleset,
        sale_delay_days=365,
        active_comparable_depth=1,
        dispersion_subscore=Decimal("10"),
        brand_concentration_rate=Decimal("0.05"),
    )
    assert result.liquidity < Decimal("40")
    assert result.subscores["diversification"] == Decimal("50")
    assert "illiquid_diversification" in [cap.name for cap in result.applied_caps]


def test_long_delay_with_high_allocation_forces_pass(ruleset: Ruleset) -> None:
    result = _score(
        ruleset,
        sale_delay_days=200,
        allocation_rate=Decimal("0.60"),
        maximum_allocation_rate=Decimal("0.80"),
    )
    assert result.verdict is Verdict.PASS
    assert "long_delay_with_high_allocation" in result.blocking_conditions


def test_strict_allocation_requires_stronger_evidence(ruleset: Ruleset) -> None:
    result = _score(
        ruleset,
        allocation_rate=Decimal("0.40"),
        maximum_allocation_rate=Decimal("0.50"),
        valuation_confidence=Decimal("65"),
    )
    assert result.verdict is not Verdict.BUY
    assert "strict_allocation_requirements_unmet" in result.blocking_conditions


def test_suggested_identification_caps_the_verdict_at_watch(
    ruleset: Ruleset,
) -> None:
    result = _score(
        ruleset,
        gate_overrides={
            "reference_status": "suggested",
            "identification_confidence": Decimal("90"),
        },
    )
    assert result.verdict is Verdict.WATCH
    assert "identification_only_suggested" in result.blocking_conditions


# --- Portes et verdict ---------------------------------------------------


def test_a_blocking_gate_makes_the_analysis_impossible(ruleset: Ruleset) -> None:
    result = _score(ruleset, gate_overrides={"comparable_count": 0})
    assert result.verdict is Verdict.ANALYSIS_IMPOSSIBLE
    assert result.final_score == Decimal("0.00")
    assert "gate_failed_G4_MARKET_SUPPORT" in result.blocking_conditions


def test_authenticity_failure_forces_pass_despite_a_perfect_score(
    ruleset: Ruleset,
) -> None:
    """Une marge élevée ne compense jamais un échec de porte."""

    result = _score(
        ruleset, gate_overrides={"authenticity_signals": ("counterfeit_suspected",)}
    )
    assert result.raw_score == Decimal("100.00")
    assert result.verdict is Verdict.PASS
    assert "gate_failed_G1_AUTHENTICITY" in result.blocking_conditions


def test_the_most_cautious_verdict_wins() -> None:
    assert most_cautious(Verdict.BUY, Verdict.WATCH) is Verdict.WATCH
    assert most_cautious(Verdict.WATCH, Verdict.PASS) is Verdict.PASS
    assert most_cautious(Verdict.PASS, Verdict.ANALYSIS_IMPOSSIBLE) is Verdict.PASS
    assert most_cautious(Verdict.BUY, Verdict.BUY) is Verdict.BUY


def test_every_cap_is_kept_in_the_trace(ruleset: Ruleset) -> None:
    result = _score(
        ruleset,
        valuation_confidence=Decimal("30"),
        allocation_rate=Decimal("0.90"),
        maximum_allocation_rate=Decimal("0.50"),
        capital_immobilization_rate=Decimal("0.80"),
    )
    names = {cap.name for cap in result.applied_caps}
    assert "valuation_below_40" in names
    assert "allocation_exceeded" in names
    assert "immobilization_and_allocation" in names
    assert all(cap.reason for cap in result.applied_caps)
    # Le plus contraignant l'emporte.
    assert result.final_score == Decimal("54.00")


def test_trace_carries_the_ruleset_version(ruleset: Ruleset) -> None:
    assert _score(ruleset).ruleset_version == "1.0.0"
