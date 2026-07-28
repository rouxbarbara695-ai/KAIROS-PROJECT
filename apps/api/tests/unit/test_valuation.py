from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.market.domain.valuation import (
    WeightedPrice,
    detect_outliers,
    market_quote,
    median,
    weighted_percentile,
)
from app.shared.domain.errors import DomainError, ErrorCode
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


def _prices(*values: str) -> list[Decimal]:
    return [Decimal(value) for value in values]


def _samples(*pairs: tuple[str, str]) -> list[WeightedPrice]:
    return [
        WeightedPrice(adjusted_price_eur=Decimal(price), weight=Decimal(weight))
        for price, weight in pairs
    ]


# --- Médiane -------------------------------------------------------------


def test_median_of_odd_and_even_counts() -> None:
    assert median(_prices("10", "30", "20")) == Decimal("20")
    assert median(_prices("10", "20", "30", "40")) == Decimal("25")


def test_median_of_empty_set_is_rejected() -> None:
    with pytest.raises(DomainError):
        median([])


# --- Anomalies -----------------------------------------------------------


def test_small_sample_is_never_auto_excluded(ruleset: Ruleset) -> None:
    """Sous le seuil d'effectif, même un prix aberrant reste retenu : sur peu
    de données, l'exclusion appauvrirait davantage qu'elle ne corrige."""

    report = detect_outliers(_prices("1000", "1050", "50000"), ruleset)
    assert report.method == "not_applicable"
    assert report.flagged_count == 0


def test_modified_z_flags_an_extreme_value(ruleset: Ruleset) -> None:
    prices = _prices("1000", "1010", "1020", "1030", "9000")
    report = detect_outliers(prices, ruleset)
    assert report.method == "modified_z"
    assert report.flagged == (False, False, False, False, True)


def test_tight_cluster_flags_nothing(ruleset: Ruleset) -> None:
    report = detect_outliers(_prices("1000", "1010", "1020", "1030"), ruleset)
    assert report.method == "modified_z"
    assert report.flagged_count == 0


def test_zero_mad_falls_back_to_iqr(ruleset: Ruleset) -> None:
    """Plus de la moitié des prix identiques annule le MAD : le score modifié
    diviserait par zéro, d'où le repli sur l'écart interquartile."""

    prices = _prices("1000", "1000", "1000", "1000", "1000", "2000", "3000", "50000")
    report = detect_outliers(prices, ruleset)
    assert report.method == "iqr"
    assert report.mad == 0
    assert report.flagged[-1] is True
    assert report.flagged_count == 1


def test_iqr_fallback_tolerates_a_lone_extreme_on_tiny_samples(
    ruleset: Ruleset,
) -> None:
    """Conséquence assumée des charnières de Tukey (Q-11) : sur cinq valeurs
    dont quatre identiques, la valeur extrême tire `Q3` avec elle et retombe
    dans les bornes. Elle n'est donc pas exclue — comportement documenté, pas
    accidentel."""

    report = detect_outliers(_prices("1000", "1000", "1000", "1000", "5000"), ruleset)
    assert report.method == "iqr"
    assert report.flagged_count == 0


def test_all_identical_prices_exclude_nothing(ruleset: Ruleset) -> None:
    report = detect_outliers(_prices("1000", "1000", "1000", "1000"), ruleset)
    assert report.method == "degenerate"
    assert report.flagged_count == 0


# --- Percentiles pondérés ------------------------------------------------


def test_weighted_percentile_follows_cumulated_weight() -> None:
    samples = _samples(("100", "1"), ("200", "1"), ("300", "1"), ("400", "1"))
    assert weighted_percentile(samples, Decimal("0.50")) == Decimal("200")
    assert weighted_percentile(samples, Decimal("0.25")) == Decimal("100")
    assert weighted_percentile(samples, Decimal("0.75")) == Decimal("300")


def test_heavy_weight_pulls_the_percentile() -> None:
    """Un comparable très fiable doit dominer plusieurs comparables faibles."""

    samples = _samples(("100", "0.1"), ("200", "0.1"), ("1000", "10"))
    assert weighted_percentile(samples, Decimal("0.50")) == Decimal("1000")


def test_zero_total_weight_is_rejected() -> None:
    with pytest.raises(DomainError) as exc:
        weighted_percentile(_samples(("100", "0"), ("200", "0")), Decimal("0.50"))
    assert exc.value.code is ErrorCode.VALUATION_INSUFFICIENT_COMPARABLES


# --- Cote de marché ------------------------------------------------------


def test_single_comparable_is_refused(ruleset: Ruleset) -> None:
    with pytest.raises(DomainError) as exc:
        market_quote(_samples(("1000", "1")), ruleset)
    assert exc.value.code is ErrorCode.VALUATION_INSUFFICIENT_COMPARABLES


def test_small_sample_interval_is_widened(ruleset: Ruleset) -> None:
    samples = _samples(("1000", "1"), ("1000", "1"), ("1000", "1"))
    quote = market_quote(samples, ruleset)
    assert quote.central_eur == Decimal("1000.00")
    assert quote.low_eur == Decimal("900.00")
    assert quote.high_eur == Decimal("1100.00")
    assert quote.widened_for_small_sample is True


def test_widening_never_narrows_an_existing_interval(ruleset: Ruleset) -> None:
    """L'élargissement est un plancher, pas un remplacement : un intervalle
    déjà plus large que la marge minimale doit être conservé tel quel."""

    samples = _samples(("100", "1"), ("1000", "1"), ("5000", "1"))
    quote = market_quote(samples, ruleset)
    assert quote.low_eur <= Decimal("900.00")
    assert quote.high_eur >= Decimal("1100.00")


def test_large_sample_is_not_widened(ruleset: Ruleset) -> None:
    samples = _samples(
        ("1000", "1"), ("1010", "1"), ("1020", "1"), ("1030", "1"), ("1040", "1")
    )
    quote = market_quote(samples, ruleset)
    assert quote.widened_for_small_sample is False
    assert quote.comparable_count == 5


def test_quote_is_ordered_and_rounded(ruleset: Ruleset) -> None:
    samples = _samples(
        ("1000.005", "1"), ("1200.994", "2"), ("1500.50", "1"), ("1800.00", "1")
    )
    quote = market_quote(samples, ruleset)
    assert quote.low_eur <= quote.central_eur <= quote.high_eur
    assert quote.low_eur.as_tuple().exponent == -2
    assert quote.central_eur.as_tuple().exponent == -2
