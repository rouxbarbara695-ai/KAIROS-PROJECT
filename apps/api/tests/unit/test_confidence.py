from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.market.domain.confidence import (
    ConfidenceInput,
    valuation_confidence,
)
from app.market.domain.valuation import MarketQuote
from app.shared.domain.errors import DomainError
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


def _quote(low: str, central: str, high: str, count: int = 8) -> MarketQuote:
    return MarketQuote(
        low_eur=Decimal(low),
        central_eur=Decimal(central),
        high_eur=Decimal(high),
        comparable_count=count,
        total_weight=Decimal("1"),
        widened_for_small_sample=False,
    )


def _comparable(
    reliability: str = "a",
    recency: str = "1.00",
    seller: str = "seller-1",
    reference: str = "1.00",
    condition: str = "1.00",
    completeness: str = "1.00",
) -> ConfidenceInput:
    return ConfidenceInput(
        reliability_class=reliability,
        recency_factor=Decimal(recency),
        reference_similarity=Decimal(reference),
        condition_similarity=Decimal(condition),
        completeness_similarity=Decimal(completeness),
        seller_key=seller,
    )


def _ideal(count: int = 8) -> list[ConfidenceInput]:
    return [_comparable(seller=f"seller-{index}") for index in range(count)]


def test_ideal_evidence_reaches_one_hundred(ruleset: Ruleset) -> None:
    result = valuation_confidence(
        _ideal(),
        _quote("980", "1000", "1020"),
        identity_confirmed=True,
        ruleset=ruleset,
    )
    assert result.value == Decimal("100.00")
    assert result.applied_caps == ()


def test_components_are_weighted_as_specified(ruleset: Ruleset) -> None:
    """Volume 30 %, fiabilité 25 %, récence 20 %, similarité 15 %,
    dispersion 10 % — vérifié sur des composantes volontairement dissemblables."""

    comparables = [
        _comparable(reliability="c", recency="0.55", seller=f"s{index}")
        for index in range(8)
    ]
    result = valuation_confidence(
        comparables,
        _quote("900", "1000", "1100"),
        identity_confirmed=True,
        ruleset=ruleset,
    )

    assert result.volume_score == Decimal("100")
    assert result.source_reliability_score == Decimal("65.00")
    assert result.recency_score == Decimal("55.00")
    assert result.similarity_score == Decimal("100.00")
    assert result.dispersion_score == Decimal("80")

    expected = (
        Decimal("100") * Decimal("0.30")
        + Decimal("65") * Decimal("0.25")
        + Decimal("55") * Decimal("0.20")
        + Decimal("100") * Decimal("0.15")
        + Decimal("80") * Decimal("0.10")
    )
    assert result.uncapped_value == expected.quantize(Decimal("0.01"))


def test_reliability_is_not_recounted_through_the_weight(ruleset: Ruleset) -> None:
    """Les moyennes ignorent le poids final : la récence ne doit pas influencer
    le sous-score de fiabilité, ni l'inverse."""

    fresh = valuation_confidence(
        [
            _comparable(reliability="b", recency="1.00", seller=f"s{i}")
            for i in range(8)
        ],
        _quote("980", "1000", "1020"),
        identity_confirmed=True,
        ruleset=ruleset,
    )
    stale = valuation_confidence(
        [
            _comparable(reliability="b", recency="0.35", seller=f"s{i}")
            for i in range(8)
        ],
        _quote("980", "1000", "1020"),
        identity_confirmed=True,
        ruleset=ruleset,
    )
    assert fresh.source_reliability_score == stale.source_reliability_score
    assert fresh.recency_score != stale.recency_score


@pytest.mark.parametrize(
    ("count", "expected"),
    [(2, "30"), (3, "50"), (4, "65"), (5, "80"), (7, "80"), (8, "100"), (20, "100")],
)
def test_volume_scale(count: int, expected: str, ruleset: Ruleset) -> None:
    result = valuation_confidence(
        _ideal(count),
        _quote("980", "1000", "1020"),
        identity_confirmed=True,
        ruleset=ruleset,
    )
    assert result.volume_score == Decimal(expected)


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        ("950", "1050", "100"),
        ("900", "1100", "80"),
        ("870", "1130", "60"),
        ("800", "1200", "35"),
        ("500", "1500", "10"),
    ],
)
def test_dispersion_scale(low: str, high: str, expected: str, ruleset: Ruleset) -> None:
    result = valuation_confidence(
        _ideal(),
        _quote(low, "1000", high),
        identity_confirmed=True,
        ruleset=ruleset,
    )
    assert result.dispersion_score == Decimal(expected)


# --- Plafonds ------------------------------------------------------------


def test_absence_of_strong_evidence_caps_at_sixty_five(ruleset: Ruleset) -> None:
    comparables = [_comparable(reliability="c", seller=f"s{i}") for i in range(8)]
    result = valuation_confidence(
        comparables,
        _quote("980", "1000", "1020"),
        identity_confirmed=True,
        ruleset=ruleset,
    )
    assert result.value == Decimal("65.00")
    assert [cap.name for cap in result.applied_caps] == ["no_ab"]
    assert result.uncapped_value > result.value


def test_unconfirmed_identity_caps_at_forty(ruleset: Ruleset) -> None:
    result = valuation_confidence(
        _ideal(),
        _quote("980", "1000", "1020"),
        identity_confirmed=False,
        ruleset=ruleset,
    )
    assert result.value == Decimal("40.00")


def test_single_seller_caps_at_thirty_five(ruleset: Ruleset) -> None:
    comparables = [_comparable(seller="unique") for _ in range(8)]
    result = valuation_confidence(
        comparables,
        _quote("980", "1000", "1020"),
        identity_confirmed=True,
        ruleset=ruleset,
    )
    assert result.value == Decimal("35.00")


def test_every_applicable_cap_is_kept_and_the_strictest_wins(
    ruleset: Ruleset,
) -> None:
    """« Tous conservés » : la trace liste chaque plafond applicable, et la
    valeur retenue est la plus contraignante — pas la dernière évaluée."""

    comparables = [_comparable(reliability="d", seller="unique") for _ in range(2)]
    result = valuation_confidence(
        comparables,
        _quote("980", "1000", "1020"),
        identity_confirmed=False,
        ruleset=ruleset,
    )

    names = [cap.name for cap in result.applied_caps]
    assert names == [
        "no_ab",
        "two_comparables",
        "identity_unconfirmed",
        "single_seller",
    ]
    assert result.value == Decimal("35.00")
    assert all(cap.reason for cap in result.applied_caps)


def test_trace_carries_the_ruleset_version(ruleset: Ruleset) -> None:
    result = valuation_confidence(
        _ideal(),
        _quote("980", "1000", "1020"),
        identity_confirmed=True,
        ruleset=ruleset,
    )
    assert result.ruleset_version == "1.0.0"


def test_empty_comparables_are_rejected(ruleset: Ruleset) -> None:
    with pytest.raises(DomainError):
        valuation_confidence(
            [], _quote("980", "1000", "1020"), identity_confirmed=True, ruleset=ruleset
        )


def test_null_central_quote_is_rejected(ruleset: Ruleset) -> None:
    with pytest.raises(DomainError):
        valuation_confidence(
            _ideal(),
            _quote("0", "0", "0"),
            identity_confirmed=True,
            ruleset=ruleset,
        )
