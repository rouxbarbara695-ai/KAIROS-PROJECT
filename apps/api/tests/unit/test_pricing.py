from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.pricing.domain.costs import (
    Cost,
    CostMode,
    CostPhase,
    Scenario,
    evaluate_scenario,
    summarise_costs,
)
from app.pricing.domain.max_price import max_purchase_price
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


def _cost(
    label: str,
    mode: CostMode,
    phase: CostPhase,
    low: str,
    central: str,
    high: str,
) -> Cost:
    return Cost(
        label=label,
        mode=mode,
        phase=phase,
        low=Decimal(low),
        central=Decimal(central),
        high=Decimal(high),
    )


# --- Scénarios -----------------------------------------------------------


def test_prudent_takes_high_costs_favorable_takes_low() -> None:
    """Le scénario ne choisit pas seulement un prix de vente : il choisit aussi
    le côté défavorable ou favorable de chaque coût."""

    costs = [
        _cost("Révision", CostMode.FIXED, CostPhase.PREPARATION, "100", "200", "300")
    ]

    assert summarise_costs(costs, Scenario.PRUDENT).fixed_costs_before_sale == Decimal(
        "300.00"
    )
    assert summarise_costs(costs, Scenario.CENTRAL).fixed_costs_before_sale == Decimal(
        "200.00"
    )
    assert summarise_costs(
        costs, Scenario.FAVORABLE
    ).fixed_costs_before_sale == Decimal("100.00")


def test_rates_and_fixed_costs_are_separated_by_phase() -> None:
    costs = [
        _cost(
            "Commission achat",
            CostMode.RATE,
            CostPhase.ACQUISITION,
            "0.05",
            "0.05",
            "0.05",
        ),
        _cost("Transport", CostMode.FIXED, CostPhase.ACQUISITION, "30", "30", "30"),
        _cost(
            "Commission vente", CostMode.RATE, CostPhase.SALE, "0.10", "0.10", "0.10"
        ),
        _cost("Emballage", CostMode.FIXED, CostPhase.SALE, "15", "15", "15"),
    ]
    breakdown = summarise_costs(costs, Scenario.CENTRAL)

    assert breakdown.purchase_variable_rate == Decimal("0.05")
    assert breakdown.fixed_costs_before_sale == Decimal("30.00")
    assert breakdown.sale_variable_rate == Decimal("0.10")
    assert breakdown.fixed_sale_costs == Decimal("15.00")


def test_negative_cost_is_rejected() -> None:
    costs = [_cost("Remise", CostMode.FIXED, CostPhase.SALE, "-10", "-10", "-10")]
    with pytest.raises(DomainError):
        summarise_costs(costs, Scenario.CENTRAL)


def test_profit_and_roi_follow_the_specification() -> None:
    costs = [
        _cost(
            "Commission achat",
            CostMode.RATE,
            CostPhase.ACQUISITION,
            "0.05",
            "0.05",
            "0.05",
        ),
        _cost("Révision", CostMode.FIXED, CostPhase.PREPARATION, "200", "200", "200"),
        _cost(
            "Commission vente", CostMode.RATE, CostPhase.SALE, "0.10", "0.10", "0.10"
        ),
    ]
    result = evaluate_scenario(
        scenario=Scenario.CENTRAL,
        purchase_price_eur=Decimal("3000.00"),
        sale_price_eur=Decimal("4000.00"),
        costs=costs,
    )

    # 3000 × 1.05 + 200 = 3350
    assert result.total_cost_before_sale_eur == Decimal("3350.00")
    # 4000 − 400 = 3600
    assert result.net_sale_proceeds_eur == Decimal("3600.00")
    assert result.net_profit_eur == Decimal("250.00")
    assert result.roi is not None
    assert result.roi.quantize(Decimal("0.0001")) == Decimal("0.0746")


def test_zero_cost_makes_roi_undefined_rather_than_infinite() -> None:
    result = evaluate_scenario(
        scenario=Scenario.CENTRAL,
        purchase_price_eur=Decimal("0"),
        sale_price_eur=Decimal("500.00"),
        costs=[],
    )
    assert result.roi is None
    assert result.roi_undefined_reason == "ROI_UNDEFINED_ZERO_COST"
    assert result.net_profit_eur == Decimal("500.00")


# --- Prix maximal d'achat ------------------------------------------------


def test_closed_form_respects_the_profit_constraint(ruleset: Ruleset) -> None:
    result = max_purchase_price(
        net_sale_proceeds_eur=Decimal("4000.00"),
        prudent_costs=[
            _cost(
                "Révision", CostMode.FIXED, CostPhase.PREPARATION, "200", "200", "200"
            )
        ],
        minimum_profit_eur=Decimal("300.00"),
        minimum_roi=Decimal("0"),
        ruleset=ruleset,
    )
    # (4000 − 200 − 300) / 1 = 3500
    assert result.raw_value_eur == Decimal("3500.00")
    assert result.solver == "closed_form"
    assert result.binding_constraint == "profit"


def test_roi_constraint_can_dominate(ruleset: Ruleset) -> None:
    result = max_purchase_price(
        net_sale_proceeds_eur=Decimal("4000.00"),
        prudent_costs=[],
        minimum_profit_eur=Decimal("0"),
        minimum_roi=Decimal("0.20"),
        ruleset=ruleset,
    )
    # 4000 / 1.2 = 3333.33
    assert result.binding_constraint == "roi"
    assert result.raw_value_eur == Decimal("3333.33")


def test_rounding_is_always_downward(ruleset: Ruleset) -> None:
    """Arrondir vers le haut proposerait un prix qu'on ne peut pas défendre."""

    result = max_purchase_price(
        net_sale_proceeds_eur=Decimal("4000.00"),
        prudent_costs=[],
        minimum_profit_eur=Decimal("0"),
        minimum_roi=Decimal("0.20"),
        ruleset=ruleset,
    )
    assert result.increment_eur == Decimal("25")
    assert result.value_eur == Decimal("3325")
    assert result.value_eur <= result.raw_value_eur


@pytest.mark.parametrize(
    ("net", "expected_increment"),
    [("1500", "10"), ("3000", "25"), ("9000", "50")],
)
def test_increment_follows_the_price_band(
    net: str, expected_increment: str, ruleset: Ruleset
) -> None:
    result = max_purchase_price(
        net_sale_proceeds_eur=Decimal(net),
        prudent_costs=[],
        minimum_profit_eur=Decimal("0"),
        minimum_roi=Decimal("0"),
        ruleset=ruleset,
    )
    assert result.increment_eur == Decimal(expected_increment)


def test_impossible_constraints_yield_zero(ruleset: Ruleset) -> None:
    result = max_purchase_price(
        net_sale_proceeds_eur=Decimal("100.00"),
        prudent_costs=[
            _cost(
                "Révision", CostMode.FIXED, CostPhase.PREPARATION, "500", "500", "500"
            )
        ],
        minimum_profit_eur=Decimal("300.00"),
        minimum_roi=Decimal("0"),
        ruleset=ruleset,
    )
    assert result.value_eur == Decimal("0")


def test_binary_search_handles_a_non_linear_fee(ruleset: Ruleset) -> None:
    """Une commission plafonnée n'est plus linéaire : la forme fermée cesse
    d'être valable et le solveur prend le relais."""

    def cost_of_purchase(price: Decimal) -> Decimal:
        fee = min(price * Decimal("0.10"), Decimal("200"))
        return price + fee + Decimal("100")

    result = max_purchase_price(
        net_sale_proceeds_eur=Decimal("4000.00"),
        prudent_costs=[],
        minimum_profit_eur=Decimal("300.00"),
        minimum_roi=Decimal("0"),
        ruleset=ruleset,
        cost_of_purchase=cost_of_purchase,
    )

    assert result.solver == "binary_search"
    assert result.iterations > 0
    # La solution doit tenir la contrainte, pas seulement s'en approcher.
    assert Decimal("4000") - cost_of_purchase(result.raw_value_eur) >= Decimal("300")
    assert result.value_eur <= result.raw_value_eur


def test_binary_search_reports_infeasibility(ruleset: Ruleset) -> None:
    def cost_of_purchase(price: Decimal) -> Decimal:
        return price + Decimal("5000")

    result = max_purchase_price(
        net_sale_proceeds_eur=Decimal("1000.00"),
        prudent_costs=[],
        minimum_profit_eur=Decimal("100.00"),
        minimum_roi=Decimal("0"),
        ruleset=ruleset,
        cost_of_purchase=cost_of_purchase,
    )
    assert result.value_eur == Decimal("0")
    assert result.binding_constraint == "infeasible"
