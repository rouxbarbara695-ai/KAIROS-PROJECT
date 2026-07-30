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


# --- TVA sur commission et frais de paiement -----------------------------


def test_vat_on_commission_is_a_cost_of_its_own() -> None:
    """Une commission de 12,5 % coûte 15 % à un vendeur qui ne récupère pas la
    taxe. La TVA figure en ligne distincte plutôt que fondue dans le taux :
    c'est la seule ligne que change un changement de statut fiscal, et elle
    doit rester lisible."""

    costs = costs_from_platform(
        PlatformFees(
            seller_fee_rate=Decimal("0.125"),
            seller_fee_fixed=Decimal("10"),
            seller_fee_vat_rate=Decimal("0.20"),
        ),
        label="Catawiki",
    )

    labels = {cost.label for cost in costs}
    assert "Catawiki — TVA sur commission vente" in labels
    assert "Catawiki — TVA sur frais fixes vente" in labels

    breakdown = summarise_costs(costs, Scenario.CENTRAL)
    assert breakdown.sale_variable_rate == Decimal("0.15")
    assert breakdown.fixed_sale_costs == Decimal("12.00")


def test_an_unstated_vat_rate_adds_nothing_and_shows_nothing() -> None:
    """Une TVA non renseignée n'est pas une TVA nulle. Rien n'est ajouté — on
    n'invente pas un taux (règle 1) — et aucune ligne n'apparaît, de sorte que
    l'absence se voit au lieu d'être comblée."""

    costs = costs_from_platform(
        PlatformFees(seller_fee_rate=Decimal("0.065")), label="Chrono24"
    )

    assert all("TVA" not in cost.label for cost in costs)
    assert summarise_costs(costs, Scenario.CENTRAL).sale_variable_rate == Decimal(
        "0.065"
    )


def test_payment_fees_are_charged_on_the_sale() -> None:
    """Les frais de paiement sont prélevés sur l'encaissement : les compter à
    l'acquisition les appliquerait au prix d'achat, donc au mauvais montant."""

    costs = costs_from_platform(
        PlatformFees(payment_fee_rate=Decimal("0.03")), label="Vestiaire"
    )

    (cost,) = costs
    assert cost.mode is CostMode.RATE
    assert cost.phase is CostPhase.SALE
    assert cost.central == Decimal("0.03")


def test_payment_fees_carry_no_vat() -> None:
    """Ce sont des frais financiers : leur appliquer la TVA de la commission
    inventerait une taxe que la plateforme ne facture pas."""

    costs = costs_from_platform(
        PlatformFees(
            payment_fee_rate=Decimal("0.03"),
            seller_fee_vat_rate=Decimal("0.20"),
        ),
        label="Vestiaire",
    )

    assert summarise_costs(costs, Scenario.CENTRAL).sale_variable_rate == Decimal(
        "0.03"
    )


def test_the_solver_pays_vat_on_the_buyer_commission() -> None:
    """Le solveur reconstruit les frais acheteur à chaque essai de prix. S'il
    ignorait la TVA que le détail des coûts applique, le prix maximal serait
    plus élevé que ce que l'opération supporte réellement."""

    fees = PlatformFees(
        buyer_fee_rate=Decimal("0.09"),
        buyer_fee_max=Decimal("500"),
        buyer_fee_vat_rate=Decimal("0.20"),
    )
    cost_of = buyer_cost_function(fees, Decimal("0"))
    assert cost_of is not None

    # 1 000 € + 9 % = 90 € de commission, majorée de 20 % de TVA = 108 €.
    assert cost_of(Decimal("1000")) == Decimal("1108.00")


def test_vat_applies_to_the_capped_commission_not_the_theoretical_one() -> None:
    """C'est le montant facturé qui est taxé. Taxer la commission avant
    plafonnement gonflerait un coût que la plateforme ne réclame pas."""

    fees = PlatformFees(
        buyer_fee_rate=Decimal("0.09"),
        buyer_fee_max=Decimal("100"),
        buyer_fee_vat_rate=Decimal("0.20"),
    )
    cost_of = buyer_cost_function(fees, Decimal("0"))
    assert cost_of is not None

    # 9 % de 5 000 € vaudraient 450 €, plafonnés à 100 € : la TVA porte sur 100.
    assert cost_of(Decimal("5000")) == Decimal("5120.00")
