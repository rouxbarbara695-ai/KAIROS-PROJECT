from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.scoring.domain.gates import (
    GateCode,
    GateInputs,
    GateStatus,
    evaluate_gates,
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


def _inputs(**overrides: object) -> GateInputs:
    base: dict = {
        "reference_status": "confirmed",
        "identification_confidence": Decimal("95"),
        "has_price": True,
        "has_currency": True,
        "has_condition": True,
        "has_completeness": True,
        "has_seller_country": True,
        "comparable_count": 4,
        "total_weight": Decimal("3.4"),
        "authenticity_signals": (),
        "seller_risk_level": "low",
    }
    base.update(overrides)
    return GateInputs(**base)  # type: ignore[arg-type]


def test_a_complete_file_passes_every_gate(ruleset: Ruleset) -> None:
    report = evaluate_gates(_inputs(), ruleset)
    assert report.passed
    assert report.analysis_possible
    assert len(report.results) == 5
    assert all(r.status is GateStatus.PASSED for r in report.results)


def test_every_gate_is_evaluated_even_after_a_failure(ruleset: Ruleset) -> None:
    """Masquer les portes suivantes priverait l'utilisateur de la liste
    complète de ce qu'il a à corriger."""

    report = evaluate_gates(
        _inputs(reference_status="unknown", has_price=False, comparable_count=0),
        ruleset,
    )
    assert len(report.results) == 5
    assert not any(r.status is GateStatus.NOT_EVALUATED for r in report.results)
    assert set(report.failed_codes) == {
        GateCode.IDENTIFICATION,
        GateCode.DATA_QUALITY,
        GateCode.MARKET_SUPPORT,
    }


# --- G1 Authenticité -----------------------------------------------------


def test_authenticity_signal_fails_the_gate(ruleset: Ruleset) -> None:
    report = evaluate_gates(
        _inputs(authenticity_signals=("counterfeit_suspected",)), ruleset
    )
    gate = report.get(GateCode.AUTHENTICITY)
    assert gate is not None
    assert gate.status is GateStatus.FAILED
    assert gate.reason_codes == ("counterfeit_suspected",)


def test_authenticity_failure_does_not_block_the_analysis(
    ruleset: Ruleset,
) -> None:
    """Une authenticité douteuse conduit à `pass` — un refus argumenté — et non
    à `analysis_impossible`, qui signifie qu'on ne peut pas se prononcer."""

    report = evaluate_gates(
        _inputs(authenticity_signals=("provenance_incompatible",)), ruleset
    )
    assert not report.passed
    assert report.analysis_possible


# --- G2 Identification ---------------------------------------------------


@pytest.mark.parametrize("status", ["confirmed", "corrected"])
def test_confirmed_reference_passes(status: str, ruleset: Ruleset) -> None:
    report = evaluate_gates(_inputs(reference_status=status), ruleset)
    gate = report.get(GateCode.IDENTIFICATION)
    assert gate is not None and gate.status is GateStatus.PASSED


def test_strong_suggestion_passes_with_warning(ruleset: Ruleset) -> None:
    report = evaluate_gates(
        _inputs(reference_status="suggested", identification_confidence=Decimal("80")),
        ruleset,
    )
    gate = report.get(GateCode.IDENTIFICATION)
    assert gate is not None
    assert gate.status is GateStatus.PASSED_WITH_WARNING
    assert report.analysis_possible


def test_weak_suggestion_fails(ruleset: Ruleset) -> None:
    report = evaluate_gates(
        _inputs(reference_status="suggested", identification_confidence=Decimal("79")),
        ruleset,
    )
    gate = report.get(GateCode.IDENTIFICATION)
    assert gate is not None and gate.status is GateStatus.FAILED
    assert not report.analysis_possible


def test_unconfirmed_reference_makes_the_analysis_impossible(
    ruleset: Ruleset,
) -> None:
    report = evaluate_gates(_inputs(reference_status="unconfirmed"), ruleset)
    assert not report.analysis_possible


# --- G3 Qualité des données ----------------------------------------------


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("has_price", "price_missing"),
        ("has_currency", "currency_missing"),
        ("has_condition", "condition_missing"),
        ("has_completeness", "completeness_missing"),
        ("has_seller_country", "seller_country_missing"),
    ],
)
def test_each_missing_field_is_named(field: str, reason: str, ruleset: Ruleset) -> None:
    report = evaluate_gates(_inputs(**{field: False}), ruleset)
    gate = report.get(GateCode.DATA_QUALITY)
    assert gate is not None
    assert gate.status is GateStatus.FAILED
    assert reason in gate.reason_codes


def test_several_missing_fields_are_all_reported(ruleset: Ruleset) -> None:
    report = evaluate_gates(_inputs(has_price=False, has_condition=False), ruleset)
    gate = report.get(GateCode.DATA_QUALITY)
    assert gate is not None
    assert set(gate.reason_codes) == {"price_missing", "condition_missing"}


# --- G4 Support de marché ------------------------------------------------


def test_too_few_comparables_fails(ruleset: Ruleset) -> None:
    report = evaluate_gates(_inputs(comparable_count=1), ruleset)
    gate = report.get(GateCode.MARKET_SUPPORT)
    assert gate is not None and gate.status is GateStatus.FAILED
    assert "insufficient_comparables" in gate.reason_codes


def test_null_total_weight_fails_even_with_enough_comparables(
    ruleset: Ruleset,
) -> None:
    """Des comparables sans poids ne documentent rien : le compte ne suffit
    pas, la somme des poids doit être strictement positive."""

    report = evaluate_gates(
        _inputs(comparable_count=8, total_weight=Decimal("0")), ruleset
    )
    gate = report.get(GateCode.MARKET_SUPPORT)
    assert gate is not None and gate.status is GateStatus.FAILED
    assert "total_weight_not_positive" in gate.reason_codes


# --- G5 Risque vendeur ---------------------------------------------------


def test_high_seller_risk_fails(ruleset: Ruleset) -> None:
    report = evaluate_gates(_inputs(seller_risk_level="high"), ruleset)
    gate = report.get(GateCode.SELLER_RISK)
    assert gate is not None and gate.status is GateStatus.FAILED
    assert report.analysis_possible


@pytest.mark.parametrize("level", ["medium", "unknown"])
def test_medium_or_unknown_seller_risk_warns(level: str, ruleset: Ruleset) -> None:
    report = evaluate_gates(_inputs(seller_risk_level=level), ruleset)
    gate = report.get(GateCode.SELLER_RISK)
    assert gate is not None
    assert gate.status is GateStatus.PASSED_WITH_WARNING
    assert report.passed


def test_gate_codes_are_stable_identifiers() -> None:
    """Les codes sont publics : les renommer casserait les intégrations et
    l'historique déjà écrit."""

    assert [code.value for code in GateCode] == [
        "G1_AUTHENTICITY",
        "G2_IDENTIFICATION",
        "G3_DATA_QUALITY",
        "G4_MARKET_SUPPORT",
        "G5_SELLER_RISK",
    ]
