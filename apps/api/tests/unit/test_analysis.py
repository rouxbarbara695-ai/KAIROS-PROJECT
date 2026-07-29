from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.portfolio.domain.exposure import PortfolioPosition
from app.pricing.domain.costs import Cost, CostMode, CostPhase, Scenario
from app.pricing.domain.platform_costs import PlatformFees
from app.scoring.application.analysis_inputs import (
    MarketFacts,
    StrategyTerms,
    TransactionCosts,
    WatchFacts,
    analyse,
)
from app.scoring.domain.gates import GateCode, GateStatus
from app.scoring.domain.score import Verdict
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


def _watch(**overrides: object) -> WatchFacts:
    base: dict = {
        "reference_status": "confirmed",
        "identification_confidence": Decimal("95"),
        "mechanical": "verified",
        "cosmetic": "excellent",
        "completeness": "full_set",
        "originality": "original",
        "seller_country": "FR",
        "seller_risk_level": "low",
        "seller_reliability": "verified",
        "transaction_protections": "authentication_and_escrow",
        "authenticity_signals": (),
    }
    base.update(overrides)
    return WatchFacts(**base)  # type: ignore[arg-type]


def _market(**overrides: object) -> MarketFacts:
    base: dict = {
        "low_eur": Decimal("3200"),
        "central_eur": Decimal("3600"),
        "high_eur": Decimal("4000"),
        "valuation_confidence": Decimal("82"),
        "comparable_count": 8,
        "total_weight": Decimal("6"),
        "active_comparable_depth": 20,
        "dispersion_subscore": Decimal("85"),
        "sale_delay_days": 21,
    }
    base.update(overrides)
    return MarketFacts(**base)  # type: ignore[arg-type]


def _terms(**overrides: object) -> StrategyTerms:
    base: dict = {
        "minimum_roi": Decimal("0.20"),
        "minimum_profit_eur": Decimal("300"),
        "maximum_allocation_rate": Decimal("0.50"),
        "negotiation_buffer": Decimal("0.05"),
    }
    base.update(overrides)
    return StrategyTerms(**base)  # type: ignore[arg-type]


def _position(cash: str = "20000", stock: str = "5000", brand: str = "2000"):
    return PortfolioPosition(
        available_cash_eur=Decimal(cash),
        stock_at_cost_eur=Decimal(stock),
        brand_exposure_at_cost_eur=Decimal(brand),
    )


_FEES = PlatformFees(
    buyer_fee_rate=Decimal("0.05"),
    seller_fee_rate=Decimal("0.10"),
    seller_fee_fixed=Decimal("20"),
)


def _costs(fees: PlatformFees = _FEES, **overrides: object) -> TransactionCosts:
    base: dict = {
        "platform_fees": fees,
        "platform_label": "Catawiki",
        "outbound_shipping_eur": Decimal("30"),
    }
    base.update(overrides)
    return TransactionCosts(**base)  # type: ignore[arg-type]


def _analyse(ruleset: Ruleset, price: str = "2400", **overrides: object):
    kwargs: dict = {
        "purchase_price_eur": Decimal(price),
        "watch": _watch(),
        "market": _market(),
        "terms": _terms(),
        "position": _position(),
        "transaction_costs": _costs(),
        "listing_quality_score": Decimal("80"),
        "ruleset": ruleset,
    }
    kwargs.update(overrides)
    return analyse(**kwargs)


# --- Enchaînement --------------------------------------------------------


def test_a_sound_case_reaches_a_verdict(ruleset: Ruleset) -> None:
    outcome = _analyse(ruleset)

    assert outcome.gates.analysis_possible
    assert outcome.gates.passed
    assert outcome.score.verdict in {Verdict.BUY, Verdict.WATCH}
    assert outcome.score.ruleset_version == "1.0.0"


def test_the_three_scenarios_are_all_evaluated(ruleset: Ruleset) -> None:
    """Prudent, central et favorable ne sont pas trois variantes de confort :
    le prix maximal se calcule sur le prudent, le score sur le central."""

    outcome = _analyse(ruleset)

    assert set(outcome.scenarios) == set(Scenario)
    prudent = outcome.scenarios[Scenario.PRUDENT]
    central = outcome.scenarios[Scenario.CENTRAL]
    favorable = outcome.scenarios[Scenario.FAVORABLE]

    assert prudent.sale_price_eur == Decimal("3200")
    assert central.sale_price_eur == Decimal("3600")
    assert favorable.sale_price_eur == Decimal("4000")
    assert prudent.net_profit_eur < central.net_profit_eur < favorable.net_profit_eur


def test_the_purchase_price_is_the_same_in_every_scenario(ruleset: Ruleset) -> None:
    """Seul le prix de revente varie : le prix d'achat est un fait, pas une
    hypothèse."""

    outcome = _analyse(ruleset, price="2400")
    assert {s.purchase_price_eur for s in outcome.scenarios.values()} == {
        Decimal("2400")
    }


def test_a_blocking_gate_forbids_any_purchase_verdict(ruleset: Ruleset) -> None:
    """Le score ne doit jamais pouvoir contredire une porte déjà fermée."""

    outcome = _analyse(ruleset, watch=_watch(reference_status="unknown"))

    assert not outcome.gates.analysis_possible
    assert GateCode.IDENTIFICATION in outcome.gates.failed_codes
    assert outcome.score.verdict is Verdict.ANALYSIS_IMPOSSIBLE


def test_a_thin_market_blocks_the_analysis(ruleset: Ruleset) -> None:
    outcome = _analyse(
        ruleset, market=_market(comparable_count=1, total_weight=Decimal("0.5"))
    )
    assert GateCode.MARKET_SUPPORT in outcome.gates.failed_codes
    assert outcome.score.verdict is Verdict.ANALYSIS_IMPOSSIBLE


def test_a_risky_seller_closes_a_gate_without_blocking_the_analysis(
    ruleset: Ruleset,
) -> None:
    """La porte vendeur interdit l'achat mais laisse l'analyse se faire : on
    doit pouvoir dire pourquoi on renonce, pas seulement qu'on renonce."""

    outcome = _analyse(ruleset, watch=_watch(seller_risk_level="high"))

    assert outcome.gates.analysis_possible
    assert not outcome.gates.passed
    assert GateCode.SELLER_RISK in outcome.gates.failed_codes
    assert outcome.score.verdict is Verdict.PASS


# --- Prix maximal --------------------------------------------------------


def test_the_maximum_price_is_independent_of_the_asking_price(
    ruleset: Ruleset,
) -> None:
    """Le prix maximal découle de la cote et de la stratégie. Qu'on le demande
    face à une annonce chère ou bon marché n'y change rien — sans quoi l'outil
    s'alignerait sur le vendeur."""

    cheap = _analyse(ruleset, price="1500")
    dear = _analyse(ruleset, price="3100")
    assert cheap.max_purchase.value_eur == dear.max_purchase.value_eur


def test_a_price_above_the_maximum_is_never_a_buy(ruleset: Ruleset) -> None:
    outcome = _analyse(ruleset, price="3100")
    assert outcome.max_purchase.value_eur < Decimal("3100")
    assert outcome.score.verdict is not Verdict.BUY


def test_the_maximum_price_is_rounded_down_to_its_increment(
    ruleset: Ruleset,
) -> None:
    maximum = _analyse(ruleset).max_purchase
    assert maximum.value_eur <= maximum.raw_value_eur
    assert maximum.value_eur % maximum.increment_eur == 0


def test_bounded_buyer_fees_switch_the_solver(ruleset: Ruleset) -> None:
    """Un plafond de commission détruit la linéarité : la forme fermée cesse
    d'être valide et le solveur binaire doit prendre le relais."""

    linear = _analyse(ruleset)
    assert linear.max_purchase.solver == "closed_form"

    bounded_fees = PlatformFees(
        buyer_fee_rate=Decimal("0.05"),
        buyer_fee_max=Decimal("80"),
        seller_fee_rate=Decimal("0.10"),
        seller_fee_fixed=Decimal("20"),
    )
    bounded = _analyse(ruleset, transaction_costs=_costs(bounded_fees))
    assert bounded.max_purchase.solver == "binary_search"
    # Un plafond réduit le coût d'acquisition : on peut payer davantage.
    assert bounded.max_purchase.value_eur > linear.max_purchase.value_eur


def test_platform_fees_are_never_counted_twice(ruleset: Ruleset) -> None:
    """Le solveur refait varier les frais acheteur avec le prix. S'ils
    figuraient aussi dans les coûts déjà agrégés qu'on lui transmet, le maximum
    sortirait mécaniquement trop bas — c'est exactement l'erreur que la
    composition des coûts rend impossible."""

    capped = PlatformFees(
        buyer_fee_rate=Decimal("0.05"), buyer_fee_max=Decimal("10000")
    )
    uncapped = PlatformFees(buyer_fee_rate=Decimal("0.05"))

    # Un plafond hors d'atteinte ne change rien au coût réel : seul le solveur
    # change. Les deux chemins doivent donc converger vers le même prix.
    binary = _analyse(ruleset, transaction_costs=_costs(capped))
    closed = _analyse(ruleset, transaction_costs=_costs(uncapped))

    assert binary.max_purchase.solver == "binary_search"
    assert closed.max_purchase.solver == "closed_form"
    assert binary.max_purchase.value_eur == closed.max_purchase.value_eur


def test_a_purchase_cost_proportional_to_the_price_is_refused(
    ruleset: Ruleset,
) -> None:
    """Le solveur ne sait faire varier que les frais de plateforme. Un coût
    opérationnel proportionnel au prix d'achat le rendrait faux en silence :
    mieux vaut refuser."""

    proportional = Cost(
        label="Commission d'apporteur",
        mode=CostMode.RATE,
        phase=CostPhase.ACQUISITION,
        low=Decimal("0.02"),
        central=Decimal("0.02"),
        high=Decimal("0.02"),
    )
    fees = PlatformFees(buyer_fee_rate=Decimal("0.05"), buyer_fee_max=Decimal("80"))

    with pytest.raises(DomainError):
        _analyse(
            ruleset,
            transaction_costs=_costs(fees, operational=(proportional,)),
        )


def test_operational_costs_reach_the_scenarios(ruleset: Ruleset) -> None:
    """Révision et polissage sont exceptionnels mais, quand ils existent, ils
    amputent le profit de tous les scénarios."""

    overhaul = Cost(
        label="Révision",
        mode=CostMode.FIXED,
        phase=CostPhase.ACQUISITION,
        low=Decimal("400"),
        central=Decimal("300"),
        high=Decimal("200"),
    )
    without = _analyse(ruleset)
    with_overhaul = _analyse(ruleset, transaction_costs=_costs(operational=(overhaul,)))

    central_gap = (
        without.scenarios[Scenario.CENTRAL].net_profit_eur
        - with_overhaul.scenarios[Scenario.CENTRAL].net_profit_eur
    )
    assert central_gap == Decimal("300.00")
    assert with_overhaul.max_purchase.value_eur < without.max_purchase.value_eur


# --- Prix affiché --------------------------------------------------------


def test_the_listing_price_applies_the_negotiation_buffer(ruleset: Ruleset) -> None:
    outcome = _analyse(ruleset, terms=_terms(negotiation_buffer=Decimal("0.05")))
    # 3600 × 1,05 = 3780, sous la borne haute de 4000.
    assert outcome.listing_price_eur == Decimal("3780.00")


def test_the_buffer_never_pushes_the_price_past_the_high_bound(
    ruleset: Ruleset,
) -> None:
    """Afficher au-delà de la borne haute reviendrait à sortir de la cote qu'on
    vient d'établir."""

    outcome = _analyse(ruleset, terms=_terms(negotiation_buffer=Decimal("0.50")))
    assert outcome.listing_price_eur == Decimal("4000.00")


# --- Portefeuille --------------------------------------------------------


def test_exposure_rates_come_from_the_real_position(ruleset: Ruleset) -> None:
    outcome = _analyse(ruleset, price="2400", position=_position())

    # 2400 / 20000 — l'allocation se mesure sur la trésorerie.
    assert outcome.allocation_rate.quantize(Decimal("0.0001")) == Decimal("0.1200")
    # (2000 + 2400) / 25000 — la concentration sur le capital total.
    assert outcome.brand_concentration_rate.quantize(Decimal("0.0001")) == Decimal(
        "0.1760"
    )
    # 5000 / 25000 — l'achat n'est pas encore en stock.
    assert outcome.capital_immobilization_rate.quantize(Decimal("0.0001")) == Decimal(
        "0.2000"
    )


def test_a_saturated_portfolio_caps_the_score(ruleset: Ruleset) -> None:
    """Un portefeuille immobilisé au-delà du seuil plafonne le score quelle que
    soit la qualité de l'affaire : c'est précisément l'objet de la règle."""

    healthy = _analyse(ruleset, position=_position(cash="20000", stock="5000"))
    # 60 000 / 65 000 = 92 % immobilisés et 2 400 / 5 000 = 48 % d'allocation :
    # le plafond exige les deux, un capital dormant seul ne suffit pas.
    saturated = _analyse(
        ruleset, position=_position(cash="5000", stock="60000", brand="2000")
    )

    assert saturated.score.final_score < healthy.score.final_score
    assert [cap.name for cap in saturated.score.applied_caps] == [
        "immobilization_and_allocation"
    ]
    assert saturated.score.final_score == Decimal("54")


# --- Trace ---------------------------------------------------------------


def test_the_outcome_carries_everything_the_verdict_rests_on(
    ruleset: Ruleset,
) -> None:
    """Règle 6 : une recommandation expose ses entrées, ses règles, ses
    plafonds et ses motifs. Un verdict nu serait inutilisable."""

    outcome = _analyse(ruleset)

    assert len(outcome.gates.results) == 5
    assert all(
        result.status is not GateStatus.NOT_EVALUATED
        for result in outcome.gates.results
    )
    assert outcome.score.subscores
    assert outcome.score.ruleset_version == "1.0.0"
    assert outcome.max_purchase.binding_constraint
    assert outcome.max_purchase.solver
