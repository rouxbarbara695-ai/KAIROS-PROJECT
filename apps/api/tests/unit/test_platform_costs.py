from __future__ import annotations

from decimal import Decimal

import pytest

from app.pricing.domain.costs import CostMode, CostPhase, Scenario, summarise_costs
from app.pricing.domain.platform_costs import (
    FeeBasis,
    FeeTier,
    PlatformFees,
    PriceContext,
    buyer_cost_function,
    costs_from_platform,
    seller_commission,
)
from app.shared.domain.errors import DomainError


def _prices(purchase: str = "1000", sale: str = "2000", **kw: Decimal) -> PriceContext:
    return PriceContext(
        purchase_price_eur=Decimal(purchase), sale_price_eur=Decimal(sale), **kw
    )


def test_buyer_and_seller_fees_land_in_different_phases() -> None:
    """La phase détermine à quel prix la commission s'applique : intervertir
    les deux côtés rendrait le calcul silencieusement faux."""

    costs = costs_from_platform(
        PlatformFees(
            buyer_fee_rate=Decimal("0.20"),
            buyer_fee_fixed=Decimal("15"),
            seller_fee_rate=Decimal("0.10"),
            seller_fee_fixed=Decimal("5"),
        ),
        label="Catawiki",
        prices=_prices(),
    )
    breakdown = summarise_costs(costs, Scenario.CENTRAL)

    # 20 % de 1 000 € à l'achat, 10 % de 2 000 € à la vente.
    assert breakdown.fixed_costs_before_sale == Decimal("215.00")
    assert breakdown.fixed_sale_costs == Decimal("205.00")


def test_platform_fees_do_not_vary_by_scenario_at_a_given_price() -> None:
    """Une commission de plateforme est certaine : l'incertitude appartient aux
    coûts opérationnels, qui ne viennent pas d'ici. Ce qui varie d'un scénario
    à l'autre, c'est le prix — pas la règle."""

    costs = costs_from_platform(
        PlatformFees(buyer_fee_rate=Decimal("0.20")), label="Chrono24", prices=_prices()
    )
    totals = {
        scenario: summarise_costs(costs, scenario).fixed_costs_before_sale
        for scenario in Scenario
    }
    assert len(set(totals.values())) == 1


def test_absent_and_zero_fees_produce_no_cost() -> None:
    assert costs_from_platform(PlatformFees(), label="Vide", prices=_prices()) == []
    assert (
        costs_from_platform(
            PlatformFees(buyer_fee_rate=Decimal("0")), label="Zéro", prices=_prices()
        )
        == []
    )


def test_shipping_is_split_by_direction() -> None:
    costs = costs_from_platform(
        PlatformFees(),
        label="Boutique",
        prices=_prices(
            inbound_shipping_eur=Decimal("25"), outbound_shipping_eur=Decimal("18")
        ),
    )
    breakdown = summarise_costs(costs, Scenario.CENTRAL)
    assert breakdown.fixed_costs_before_sale == Decimal("25.00")
    assert breakdown.fixed_sale_costs == Decimal("18.00")


def test_costs_are_labelled_with_their_platform() -> None:
    """La trace doit dire d'où vient chaque euro."""

    costs = costs_from_platform(
        PlatformFees(buyer_fee_rate=Decimal("0.20")), label="Catawiki", prices=_prices()
    )
    assert costs[0].label == "Catawiki — commission achat"
    # Tout est émis en montant : c'est ce qui permet d'honorer tranches,
    # planchers et plafonds, qu'un taux unique ne sait pas représenter.
    assert costs[0].mode is CostMode.FIXED
    assert costs[0].phase is CostPhase.ACQUISITION


# --- Solveur du prix maximal ---------------------------------------------


def test_a_platform_without_buyer_fees_leaves_the_closed_form() -> None:
    assert buyer_cost_function(PlatformFees(), Decimal("100"), Decimal("0")) is None


def test_the_solver_takes_over_as_soon_as_a_buyer_fee_exists() -> None:
    """Une seule implémentation du coût d'achat, plutôt que deux qui
    pourraient diverger."""

    fees = PlatformFees(buyer_fee_rate=Decimal("0.20"), buyer_fee_max=Decimal("200"))
    cost_of = buyer_cost_function(fees, Decimal("100"), Decimal("0"))
    assert cost_of is not None
    # En dessous du plafond, le taux s'applique pleinement.
    assert cost_of(Decimal("500")) == Decimal("700")
    # Au-delà, la commission est figée à 200.
    assert cost_of(Decimal("5000")) == Decimal("5300")


def test_a_floor_lifts_a_small_buyer_fee() -> None:
    fees = PlatformFees(buyer_fee_rate=Decimal("0.10"), buyer_fee_min=Decimal("50"))
    cost_of = buyer_cost_function(fees, Decimal("0"), Decimal("0"))
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
    cost_of = buyer_cost_function(fees, Decimal("50"), Decimal("0"))
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
        prices=_prices(sale="1000"),
    )

    labels = {cost.label for cost in costs}
    assert "Catawiki — TVA sur frais de vente" in labels

    # 12,5 % de 1 000 € = 125 €, plus 10 € fixes, plus 20 % de TVA sur les
    # deux = 27 €. Un vendeur qui ne récupère pas la taxe paie 162 €.
    breakdown = summarise_costs(costs, Scenario.CENTRAL)
    assert breakdown.fixed_sale_costs == Decimal("162.00")


def test_an_unstated_vat_rate_adds_nothing_and_shows_nothing() -> None:
    """Une TVA non renseignée n'est pas une TVA nulle. Rien n'est ajouté — on
    n'invente pas un taux (règle 1) — et aucune ligne n'apparaît, de sorte que
    l'absence se voit au lieu d'être comblée."""

    costs = costs_from_platform(
        PlatformFees(seller_fee_rate=Decimal("0.065")),
        label="Chrono24",
        prices=_prices(sale="1000"),
    )

    assert all("TVA" not in cost.label for cost in costs)
    assert summarise_costs(costs, Scenario.CENTRAL).fixed_sale_costs == Decimal("65.00")


def test_payment_fees_are_charged_on_the_sale() -> None:
    """Les frais de paiement sont prélevés sur l'encaissement : les compter à
    l'acquisition les appliquerait au prix d'achat, donc au mauvais montant."""

    costs = costs_from_platform(
        PlatformFees(payment_fee_rate=Decimal("0.03")),
        label="Vestiaire",
        prices=_prices(sale="1000"),
    )

    (cost,) = costs
    assert cost.phase is CostPhase.SALE
    assert cost.central == Decimal("30.00")


def test_payment_fees_carry_no_vat() -> None:
    """Ce sont des frais financiers : leur appliquer la TVA de la commission
    inventerait une taxe que la plateforme ne facture pas."""

    costs = costs_from_platform(
        PlatformFees(
            payment_fee_rate=Decimal("0.03"),
            seller_fee_vat_rate=Decimal("0.20"),
        ),
        label="Vestiaire",
        prices=_prices(sale="1000"),
    )

    assert summarise_costs(costs, Scenario.CENTRAL).fixed_sale_costs == Decimal("30.00")


def test_the_solver_pays_vat_on_the_buyer_commission() -> None:
    """Le solveur reconstruit les frais acheteur à chaque essai de prix. S'il
    ignorait la TVA que le détail des coûts applique, le prix maximal serait
    plus élevé que ce que l'opération supporte réellement."""

    fees = PlatformFees(
        buyer_fee_rate=Decimal("0.09"),
        buyer_fee_max=Decimal("500"),
        buyer_fee_vat_rate=Decimal("0.20"),
    )
    cost_of = buyer_cost_function(fees, Decimal("0"), Decimal("0"))
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
    cost_of = buyer_cost_function(fees, Decimal("0"), Decimal("0"))
    assert cost_of is not None

    # 9 % de 5 000 € vaudraient 450 €, plafonnés à 100 € : la TVA porte sur 100.
    assert cost_of(Decimal("5000")) == Decimal("5120.00")


# --- Barèmes par tranches ------------------------------------------------


def _ebay_tiers() -> tuple[FeeTier, ...]:
    """Le barème réel d'eBay France pour un vendeur particulier."""

    return (
        FeeTier(up_to=Decimal("2000"), rate=Decimal("0.10")),
        FeeTier(up_to=None, rate=Decimal("0.02")),
    )


def test_tiers_apply_marginally_not_by_threshold() -> None:
    """« 10 % jusqu'à 2 000 € puis 2 % » ne fait pas basculer les 2 000
    premiers euros à 2 %. Sur 10 000 €, la lecture à seuil dirait 200 € là où
    la plateforme facture 360 €."""

    fees = PlatformFees(seller_fee_tiers=_ebay_tiers())

    assert seller_commission(fees, Decimal("10000"), Decimal("0")).variable == Decimal(
        "360.00"
    )
    # 10 % de 2 000 = 200, plus 2 % de 1 600 = 32.
    assert seller_commission(fees, Decimal("3600"), Decimal("0")).variable == Decimal(
        "232.00"
    )
    # Sous le premier palier, le taux plein s'applique à tout.
    assert seller_commission(fees, Decimal("1500"), Decimal("0")).variable == Decimal(
        "150.00"
    )


def test_the_effective_rate_falls_as_the_price_rises() -> None:
    """C'est tout l'enjeu : un taux unique se tromperait du simple au double
    d'un bout à l'autre de la fourchette."""

    fees = PlatformFees(seller_fee_tiers=_ebay_tiers())
    rates = [
        seller_commission(fees, price, Decimal("0")).variable / price
        for price in (Decimal("1500"), Decimal("10000"))
    ]
    assert rates[0] > Decimal("0.09")
    assert rates[1] < Decimal("0.04")


def test_an_incomplete_scale_is_refused_rather_than_extrapolated() -> None:
    """Prolonger le dernier taux au-delà de son plafond serait inventer une
    règle que la plateforme n'a pas publiée."""

    fees = PlatformFees(
        seller_fee_tiers=(FeeTier(up_to=Decimal("2000"), rate=Decimal("0.10")),)
    )
    with pytest.raises(DomainError):
        seller_commission(fees, Decimal("3000"), Decimal("0"))


def test_tiers_win_over_a_flat_rate() -> None:
    """Les deux ne se cumulent jamais : un barème saisi remplace le taux."""

    fees = PlatformFees(seller_fee_rate=Decimal("0.50"), seller_fee_tiers=_ebay_tiers())
    assert seller_commission(fees, Decimal("1000"), Decimal("0")).variable == Decimal(
        "100.00"
    )


# --- Base de commission --------------------------------------------------


def test_shipping_enters_the_base_only_when_the_platform_says_so() -> None:
    """eBay commissionne le port, Chrono24 non."""

    ebay = PlatformFees(
        seller_fee_rate=Decimal("0.10"),
        seller_fee_basis=FeeBasis.PRICE_AND_SHIPPING,
    )
    chrono24 = PlatformFees(seller_fee_rate=Decimal("0.10"))

    assert seller_commission(ebay, Decimal("1000"), Decimal("20")).variable == Decimal(
        "102.00"
    )
    assert seller_commission(
        chrono24, Decimal("1000"), Decimal("20")
    ).variable == Decimal("100.00")


# --- Bornes enfin honorées (POL-058) -------------------------------------


def test_a_capped_commission_is_capped_in_the_scenarios() -> None:
    """Le défaut corrigé : le plafond était saisi, stocké, transporté… puis
    ignoré au calcul des scénarios."""

    fees = PlatformFees(seller_fee_rate=Decimal("0.17"), seller_fee_max=Decimal("2500"))
    costs = costs_from_platform(
        fees,
        label="Vestiaire",
        prices=PriceContext(
            purchase_price_eur=Decimal("10000"), sale_price_eur=Decimal("20000")
        ),
    )
    breakdown = summarise_costs(costs, Scenario.CENTRAL)

    # 17 % de 20 000 € vaudraient 3 400 €, plafonnés à 2 500 €.
    assert breakdown.fixed_sale_costs == Decimal("2500.00")


def test_a_floor_lifts_a_small_commission() -> None:
    fees = PlatformFees(seller_fee_rate=Decimal("0.05"), seller_fee_min=Decimal("30"))
    assert seller_commission(fees, Decimal("200"), Decimal("0")).variable == Decimal(
        "30.00"
    )


def test_vat_applies_after_the_cap() -> None:
    """C'est le montant facturé qui est taxé, pas celui qui aurait été dû."""

    fees = PlatformFees(
        seller_fee_rate=Decimal("0.17"),
        seller_fee_max=Decimal("2500"),
        seller_fee_vat_rate=Decimal("0.20"),
    )
    breakdown = seller_commission(fees, Decimal("20000"), Decimal("0"))
    assert breakdown.variable == Decimal("2500.00")
    assert breakdown.vat == Decimal("500.00")
    assert breakdown.applied_cap is True


def test_the_solver_uses_the_tiers_too() -> None:
    """Sinon le prix maximal serait calculé sur une commission qui n'est pas
    celle que l'acheteur paiera."""

    fees = PlatformFees(buyer_fee_tiers=_ebay_tiers())
    cost_of = buyer_cost_function(fees, Decimal("0"), Decimal("0"))
    assert cost_of is not None
    # 3 000 € + 10 % de 2 000 + 2 % de 1 000 = 3 000 + 220.
    assert cost_of(Decimal("3000")) == Decimal("3220.00")


def test_no_buyer_fee_leaves_the_closed_form_available() -> None:
    assert buyer_cost_function(PlatformFees(), Decimal("0"), Decimal("0")) is None
