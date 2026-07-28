from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.market.domain.comparable import (
    BuyerFeeRule,
    adjust_for_set,
    buyer_total_price,
    comparable_weight,
    recency_factor,
)
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.rules.ruleset import Ruleset

_SEED = Path(__file__).parents[4] / "database" / "schema.sql"


@pytest.fixture(scope="module")
def ruleset() -> Ruleset:
    """Le ruleset réel du dépôt, pas une copie de test : une divergence entre
    le barème seedé et les moteurs doit faire échouer les tests."""

    sql = _SEED.read_text(encoding="utf-8")
    start = sql.index("'{", sql.index("with seed(version, config, valid_from)")) + 1
    end = sql.index("'::jsonb", start)
    config = json.loads(sql[start:end], parse_float=Decimal)
    return Ruleset(version="1.0.0", config=config)


# --- Coût acheteur -------------------------------------------------------


def test_buyer_total_price_applies_rate_fixed_and_shipping() -> None:
    cost = buyer_total_price(
        Decimal("1000.00"),
        BuyerFeeRule(rate=Decimal("0.20"), fixed=Decimal("15.00")),
        compulsory_shipping_not_included_eur=Decimal("25.00"),
    )
    assert cost.variable_fee_eur == Decimal("200.00")
    assert cost.total_eur == Decimal("1240.00")


def test_buyer_fee_is_clamped_to_minimum() -> None:
    cost = buyer_total_price(
        Decimal("100.00"), BuyerFeeRule(rate=Decimal("0.10"), minimum=Decimal("50.00"))
    )
    assert cost.variable_fee_eur == Decimal("50.00")
    assert cost.total_eur == Decimal("150.00")


def test_buyer_fee_is_clamped_to_maximum() -> None:
    cost = buyer_total_price(
        Decimal("100000.00"),
        BuyerFeeRule(rate=Decimal("0.20"), maximum=Decimal("5000.00")),
    )
    assert cost.variable_fee_eur == Decimal("5000.00")


def test_absent_bound_means_no_bound() -> None:
    """Une borne `null` n'est pas une borne à zéro : sans maximum, un gros
    montant ne doit pas voir ses frais écrasés."""

    cost = buyer_total_price(Decimal("100000.00"), BuyerFeeRule(rate=Decimal("0.20")))
    assert cost.variable_fee_eur == Decimal("20000.00")


def test_rule_without_fees_leaves_price_unchanged() -> None:
    cost = buyer_total_price(Decimal("2500.00"), BuyerFeeRule())
    assert cost.total_eur == Decimal("2500.00")


def test_negative_base_price_is_rejected() -> None:
    with pytest.raises(DomainError) as exc:
        buyer_total_price(Decimal("-1.00"), BuyerFeeRule())
    assert exc.value.code is ErrorCode.VALIDATION_ERROR


def test_monetary_output_uses_round_half_up() -> None:
    cost = buyer_total_price(Decimal("100.00"), BuyerFeeRule(rate=Decimal("0.125")))
    # 12.5 arrondi au demi supérieur, jamais au pair le plus proche.
    assert cost.variable_fee_eur == Decimal("12.50")

    cost = buyer_total_price(Decimal("10.01"), BuyerFeeRule(rate=Decimal("0.005")))
    assert cost.variable_fee_eur == Decimal("0.05")


# --- Ajustement de set ---------------------------------------------------


def test_full_set_comparable_adjusted_to_watch_only(ruleset: Ruleset) -> None:
    # 1200 / 1.20 = 1000 pour une montre seule.
    assert adjust_for_set(
        Decimal("1200.00"), "full_set", "watch_only", ruleset
    ) == Decimal("1000.00")


def test_watch_only_comparable_adjusted_to_full_set(ruleset: Ruleset) -> None:
    assert adjust_for_set(
        Decimal("1000.00"), "watch_only", "full_set", ruleset
    ) == Decimal("1200.00")


def test_identical_set_leaves_price_unchanged(ruleset: Ruleset) -> None:
    assert adjust_for_set(
        Decimal("1234.56"), "box_or_papers", "box_or_papers", ruleset
    ) == Decimal("1234.56")


def test_adjustment_never_compounds_beyond_the_scale(ruleset: Ruleset) -> None:
    """Passer de montre seule à full set applique 20 %, pas davantage, même
    en enchaînant les conversions."""

    once = adjust_for_set(Decimal("1000.00"), "watch_only", "full_set", ruleset)
    twice = adjust_for_set(once, "full_set", "full_set", ruleset)
    assert once == twice == Decimal("1200.00")


def test_unknown_completeness_fails_loudly(ruleset: Ruleset) -> None:
    with pytest.raises(DomainError) as exc:
        adjust_for_set(Decimal("1000.00"), "collector_edition", "full_set", ruleset)
    assert exc.value.code is ErrorCode.RULESET_MISSING


# --- Fraîcheur -----------------------------------------------------------


@pytest.mark.parametrize(
    ("age_days", "expected"),
    [
        (0, "1.00"),
        (30, "1.00"),
        (31, "0.90"),
        (90, "0.90"),
        (91, "0.75"),
        (180, "0.75"),
        (181, "0.55"),
        (365, "0.55"),
        (366, "0.35"),
    ],
)
def test_recency_boundaries_are_inclusive(
    age_days: int, expected: str, ruleset: Ruleset
) -> None:
    assert recency_factor(age_days, ruleset) == Decimal(expected)


def test_negative_age_is_rejected(ruleset: Ruleset) -> None:
    with pytest.raises(DomainError):
        recency_factor(-1, ruleset)


# --- Poids ---------------------------------------------------------------


def test_weight_is_the_product_of_its_factors(ruleset: Ruleset) -> None:
    factors = comparable_weight(
        reliability_class="a",
        age_days=10,
        reference_match="same",
        condition_gap="one_level",
        completeness_gap="same",
        seller_relation="independent",
        ruleset=ruleset,
    )
    assert factors.weight == Decimal("1.00000000")


def test_weakest_evidence_still_carries_a_weight(ruleset: Ruleset) -> None:
    factors = comparable_weight(
        reliability_class="e",
        age_days=400,
        reference_match="close",
        condition_gap="unknown",
        completeness_gap="unknown",
        seller_relation="probable_duplicate",
        ruleset=ruleset,
    )
    # 0.15 × 0.35 × 0.60 × 0.50 × 0.60 × 0.20
    assert factors.weight == Decimal("0.00189000")
    assert factors.weight > 0


def test_source_reliability_counted_once(ruleset: Ruleset) -> None:
    """La classe de fiabilité ne doit pas être appliquée deux fois : le poids
    d'un comparable de classe C ne diffère de celui d'un comparable de classe A
    que par le seul coefficient de fiabilité."""

    common = {
        "age_days": 10,
        "reference_match": "same",
        "condition_gap": "one_level",
        "completeness_gap": "same",
        "seller_relation": "independent",
        "ruleset": ruleset,
    }
    a = comparable_weight(reliability_class="a", **common).weight
    c = comparable_weight(reliability_class="c", **common).weight
    assert c == a * Decimal("0.65")


def test_mismatched_reference_must_be_excluded_not_weighted(
    ruleset: Ruleset,
) -> None:
    with pytest.raises(DomainError) as exc:
        comparable_weight(
            reliability_class="a",
            age_days=10,
            reference_match="other",
            condition_gap="one_level",
            completeness_gap="same",
            seller_relation="independent",
            ruleset=ruleset,
        )
    assert exc.value.code is ErrorCode.VALIDATION_ERROR
