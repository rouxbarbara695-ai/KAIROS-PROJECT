from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.market.domain.sale_delay import estimated_sale_delay
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


def _delay(ruleset: Ruleset, dated: int = 20, price: str = "3600"):
    return estimated_sale_delay(
        dated_comparables=dated,
        intended_sale_price_eur=Decimal(price),
        low_eur=Decimal("3200"),
        central_eur=Decimal("3600"),
        high_eur=Decimal("4000"),
        ruleset=ruleset,
    )


def test_a_deep_market_sold_at_the_central_price(ruleset: Ruleset) -> None:
    result = _delay(ruleset)
    assert result.depth_band == "20_plus"
    assert result.price_band == "at_or_below_central"
    # 21 jours × 1,00.
    assert result.days == 21


def test_aiming_higher_in_the_quote_costs_time(ruleset: Ruleset) -> None:
    """Viser haut n'est pas gratuit : c'est le prix demandé qui décide de la
    vitesse, pas seulement le marché."""

    cheap = _delay(ruleset, price="3200")
    central = _delay(ruleset, price="3600")
    high = _delay(ruleset, price="4000")
    above = _delay(ruleset, price="4500")

    assert cheap.days < central.days < high.days < above.days
    assert above.price_band == "above_high"


def test_a_thin_market_sells_slowly(ruleset: Ruleset) -> None:
    deep = _delay(ruleset, dated=20)
    thin = _delay(ruleset, dated=2)
    assert thin.depth_band == "under_3"
    assert thin.days > deep.days


def test_the_delay_is_bounded_at_both_ends(ruleset: Ruleset) -> None:
    """Sans plancher, un marché profond produirait un délai qu'aucune vente
    réelle ne tient ; sans plafond, un marché mince produirait un refus déguisé
    plutôt qu'une prévision."""

    fastest = _delay(ruleset, dated=50, price="1000")
    slowest = _delay(ruleset, dated=0, price="9000")

    assert fastest.days >= int(ruleset.integer("sale_delay", "minimum_days"))
    assert slowest.days <= int(ruleset.integer("sale_delay", "maximum_days"))


def test_the_bands_are_inclusive_downwards(ruleset: Ruleset) -> None:
    """Vendre *au* prix bas est le cas rapide, pas le cas limite."""

    assert _delay(ruleset, price="3200").price_band == "at_or_below_low"
    assert _delay(ruleset, price="3200.01").price_band == "at_or_below_central"
    assert _delay(ruleset, price="4000").price_band == "at_or_below_high"


def test_too_few_dated_comparables_is_flagged(ruleset: Ruleset) -> None:
    """En deçà du minimum, le délai reste calculé mais ne peut pas être
    présenté comme une prévision."""

    assert _delay(ruleset, dated=4).thin_evidence
    assert not _delay(ruleset, dated=5).thin_evidence


def test_the_result_shows_what_produced_it(ruleset: Ruleset) -> None:
    result = _delay(ruleset, dated=12, price="3900")
    assert result.base_days == 35
    assert result.multiplier == Decimal("1.35")
    # 35 × 1,35 = 47,25, arrondi à 47.
    assert result.days == 47
