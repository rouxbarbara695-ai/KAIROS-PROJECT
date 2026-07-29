from __future__ import annotations

from decimal import Decimal

from app.pricing.domain.costs import CostMode, CostPhase, Scenario, summarise_costs
from app.pricing.domain.platform_costs import (
    PlatformFees,
    buyer_cost_function,
    costs_from_platform,
)


def test_buyer_and_seller_fees_land_in_different_phases() -> None:
    """La phase détermine à quel prix le taux s'applique : intervertir les deux
    côtés rendrait le calcul silencieusement faux."""

    costs = costs_from_platform(
        PlatformFees(
            buyer_fee_rate=Decimal("0.20"),
            buyer_fee_fixed=Decimal("15"),
            seller_fee_rate=Decimal("0.10"),
            seller_fee_fixed=Decimal("5"),
        ),
        label="Catawiki",
    )
    breakdown = summarise_costs(costs, Scenario.CENTRAL)

    assert breakdown.purchase_variable_rate == Decimal("0.20")
    assert breakdown.fixed_costs_before_sale == Decimal("15.00")
    assert breakdown.sale_variable_rate == Decimal("0.10")
    assert breakdown.fixed_sale_costs == Decimal("5.00")


def test_platform_fees_do_not_vary_by_scenario() -> None:
    """Une commission de plateforme est certaine : l'incertitude appartient aux
    coûts opérationnels, qui ne viennent pas d'ici."""

    costs = costs_from_platform(
        PlatformFees(buyer_fee_rate=Decimal("0.20")), label="Chrono24"
    )
    rates = {
        scenario: summarise_costs(costs, scenario).purchase_variable_rate
        for scenario in Scenario
    }
    assert len(set(rates.values())) == 1


def test_absent_and_zero_fees_produce_no_cost() -> None:
    assert costs_from_platform(PlatformFees(), label="Vide") == []
    assert (
        costs_from_platform(PlatformFees(buyer_fee_rate=Decimal("0")), label="Zéro")
        == []
    )


def test_shipping_is_split_by_direction() -> None:
    costs = costs_from_platform(
        PlatformFees(),
        label="Boutique",
        inbound_shipping_eur=Decimal("25"),
        outbound_shipping_eur=Decimal("18"),
    )
    breakdown = summarise_costs(costs, Scenario.CENTRAL)
    assert breakdown.fixed_costs_before_sale == Decimal("25.00")
    assert breakdown.fixed_sale_costs == Decimal("18.00")


def test_costs_are_labelled_with_their_platform() -> None:
    """La trace doit dire d'où vient chaque euro."""

    costs = costs_from_platform(
        PlatformFees(buyer_fee_rate=Decimal("0.20")), label="Catawiki"
    )
    assert costs[0].label == "Catawiki — commission achat"
    assert costs[0].mode is CostMode.RATE
    assert costs[0].phase is CostPhase.ACQUISITION


# --- Linéarité et solveur ------------------------------------------------


def test_unbounded_fees_stay_linear() -> None:
    fees = PlatformFees(buyer_fee_rate=Decimal("0.20"), buyer_fee_fixed=Decimal("15"))
    assert fees.buyer_fee_is_linear
    assert buyer_cost_function(fees, Decimal("100")) is None


def test_a_capped_fee_breaks_linearity() -> None:
    """La forme fermée du prix maximal suppose une linéarité qu'un plafond
    détruit : le solveur binaire doit prendre le relais."""

    fees = PlatformFees(buyer_fee_rate=Decimal("0.20"), buyer_fee_max=Decimal("200"))
    assert not fees.buyer_fee_is_linear

    cost_of = buyer_cost_function(fees, Decimal("100"))
    assert cost_of is not None
    # En dessous du plafond, le taux s'applique pleinement.
    assert cost_of(Decimal("500")) == Decimal("700")
    # Au-delà, la commission est figée à 200.
    assert cost_of(Decimal("5000")) == Decimal("5300")


def test_a_floored_fee_breaks_linearity_too() -> None:
    fees = PlatformFees(buyer_fee_rate=Decimal("0.10"), buyer_fee_min=Decimal("50"))
    cost_of = buyer_cost_function(fees, Decimal("0"))
    assert cost_of is not None
    # 10 % de 100 € vaudrait 10 €, mais le plancher impose 50 €.
    assert cost_of(Decimal("100")) == Decimal("150")
    assert cost_of(Decimal("1000")) == Decimal("1100")


def test_the_cost_function_is_monotonic() -> None:
    """Le solveur binaire suppose une fonction croissante : sans cela, sa
    recherche n'aurait aucun sens."""

    fees = PlatformFees(
        buyer_fee_rate=Decimal("0.15"),
        buyer_fee_min=Decimal("20"),
        buyer_fee_max=Decimal("300"),
    )
    cost_of = buyer_cost_function(fees, Decimal("50"))
    assert cost_of is not None

    previous = Decimal("-1")
    for price in range(0, 5000, 250):
        current = cost_of(Decimal(price))
        assert current > previous
        previous = current
