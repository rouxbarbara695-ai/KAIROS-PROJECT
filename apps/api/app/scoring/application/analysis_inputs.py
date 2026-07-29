from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.portfolio.domain.exposure import PortfolioPosition, exposure_rates
from app.pricing.domain.costs import (
    Cost,
    CostMode,
    CostPhase,
    Scenario,
    ScenarioResult,
    evaluate_scenario,
    summarise_costs,
)
from app.pricing.domain.max_price import MaxPurchasePrice, max_purchase_price
from app.pricing.domain.platform_costs import (
    PlatformFees,
    buyer_cost_function,
    costs_from_platform,
)
from app.scoring.domain.gates import GateInputs, GateReport, evaluate_gates
from app.scoring.domain.score import ScoreInputs, ScoreResult, compute_score
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.rules.ruleset import Ruleset

_MONETARY = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class WatchFacts:
    """Ce que le dossier dit de la montre et de son vendeur."""

    reference_status: str
    identification_confidence: Decimal | None
    mechanical: str
    cosmetic: str
    completeness: str
    originality: str
    seller_country: str | None
    seller_risk_level: str
    seller_reliability: str
    transaction_protections: str
    authenticity_signals: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MarketFacts:
    """Ce que la valorisation a établi. Aucune de ces valeurs n'est recalculée
    ici : l'analyse assemble, elle ne re-décide pas."""

    low_eur: Decimal
    central_eur: Decimal
    high_eur: Decimal
    valuation_confidence: Decimal
    comparable_count: int
    total_weight: Decimal
    active_comparable_depth: int
    dispersion_subscore: Decimal
    sale_delay_days: int


@dataclass(frozen=True, slots=True)
class StrategyTerms:
    minimum_roi: Decimal
    minimum_profit_eur: Decimal
    maximum_allocation_rate: Decimal
    negotiation_buffer: Decimal


@dataclass(frozen=True, slots=True)
class TransactionCosts:
    """Ce que l'opération coûte en dehors du prix d'achat lui-même.

    Frais de plateforme et coûts opérationnels sont tenus séparés à dessein.
    Le solveur du prix maximal fait varier le prix d'achat et doit donc
    recalculer les frais acheteur à chaque essai ; s'ils figuraient aussi dans
    la liste des coûts déjà agrégés, ils seraient comptés deux fois et le
    maximum sortirait trop bas. Composer les deux ici, plutôt que de laisser
    l'appelant fournir une liste déjà fusionnée, rend cette erreur impossible.
    """

    platform_fees: PlatformFees
    platform_label: str
    inbound_shipping_eur: Decimal = Decimal("0")
    outbound_shipping_eur: Decimal = Decimal("0")
    operational: tuple[Cost, ...] = ()

    def all_costs(self) -> list[Cost]:
        """Tous les coûts, prêts pour l'évaluation des scénarios."""

        return [
            *costs_from_platform(
                self.platform_fees,
                label=self.platform_label,
                inbound_shipping_eur=self.inbound_shipping_eur,
                outbound_shipping_eur=self.outbound_shipping_eur,
            ),
            *self.operational,
        ]

    @property
    def acquisition_costs_outside_platform_fees_eur(self) -> Decimal:
        """Coûts d'acquisition que le solveur ne recalcule pas lui-même.

        `buyer_cost_function` reconstruit la commission et les frais fixes
        acheteur à partir de la grille ; tout le reste — transport entrant,
        coûts opérationnels engagés avant la vente — doit lui être fourni.
        """

        for cost in self.operational:
            if cost.mode is CostMode.RATE and cost.phase is CostPhase.ACQUISITION:
                raise DomainError(
                    ErrorCode.VALIDATION_ERROR,
                    "Un coût opérationnel proportionnel au prix d'achat ne peut "
                    "pas être résolu : le prix maximal ne saurait pas le faire "
                    f"varier ({cost.label}).",
                )

        operational_fixed = summarise_costs(
            list(self.operational), Scenario.PRUDENT
        ).fixed_costs_before_sale
        return self.inbound_shipping_eur + operational_fixed


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    gates: GateReport
    score: ScoreResult
    scenarios: dict[Scenario, ScenarioResult]
    max_purchase: MaxPurchasePrice
    listing_price_eur: Decimal
    allocation_rate: Decimal
    brand_concentration_rate: Decimal
    capital_immobilization_rate: Decimal


def _listing_price(market: MarketFacts, terms: StrategyTerms) -> Decimal:
    """`min(high, central × (1 + tampon))` : le tampon de négociation ne doit
    pas propulser le prix affiché au-delà de la borne haute de la cote."""

    with_buffer = market.central_eur * (Decimal("1") + terms.negotiation_buffer)
    return min(market.high_eur, with_buffer).quantize(_MONETARY)


def analyse(
    *,
    purchase_price_eur: Decimal,
    watch: WatchFacts,
    market: MarketFacts,
    terms: StrategyTerms,
    position: PortfolioPosition,
    transaction_costs: TransactionCosts,
    listing_quality_score: Decimal,
    ruleset: Ruleset,
) -> AnalysisOutcome:
    """Assemble portes, pricing, exposition et score.

    L'ordre est celui de la spécification — portes, valorisation, pricing,
    portefeuille, score — et il n'est pas indifférent : le score ne doit
    jamais pouvoir contredire une porte déjà fermée.
    """

    gates = evaluate_gates(
        GateInputs(
            reference_status=watch.reference_status,
            identification_confidence=watch.identification_confidence,
            has_price=purchase_price_eur > 0,
            has_currency=True,
            has_condition=bool(watch.mechanical and watch.cosmetic),
            has_completeness=bool(watch.completeness),
            has_seller_country=bool(watch.seller_country),
            comparable_count=market.comparable_count,
            total_weight=market.total_weight,
            authenticity_signals=watch.authenticity_signals,
            seller_risk_level=watch.seller_risk_level,
        ),
        ruleset,
    )

    costs = transaction_costs.all_costs()
    sale_prices = {
        Scenario.PRUDENT: market.low_eur,
        Scenario.CENTRAL: market.central_eur,
        Scenario.FAVORABLE: market.high_eur,
    }
    scenarios = {
        scenario: evaluate_scenario(
            scenario=scenario,
            purchase_price_eur=purchase_price_eur,
            sale_price_eur=sale_price,
            costs=costs,
        )
        for scenario, sale_price in sale_prices.items()
    }

    prudent = scenarios[Scenario.PRUDENT]
    central = scenarios[Scenario.CENTRAL]

    max_purchase = max_purchase_price(
        net_sale_proceeds_eur=prudent.net_sale_proceeds_eur,
        prudent_costs=costs,
        minimum_profit_eur=terms.minimum_profit_eur,
        minimum_roi=terms.minimum_roi,
        ruleset=ruleset,
        cost_of_purchase=buyer_cost_function(
            transaction_costs.platform_fees,
            transaction_costs.acquisition_costs_outside_platform_fees_eur,
        ),
    )

    rates = exposure_rates(position, purchase_price_eur)

    score = compute_score(
        ScoreInputs(
            central_profit_eur=central.net_profit_eur,
            central_roi=central.roi,
            sale_delay_days=market.sale_delay_days,
            active_comparable_depth=market.active_comparable_depth,
            dispersion_subscore=market.dispersion_subscore,
            allocation_rate=rates.allocation_rate,
            brand_concentration_rate=rates.brand_concentration_rate,
            capital_immobilization_rate=rates.capital_immobilization_rate,
            maximum_allocation_rate=terms.maximum_allocation_rate,
            mechanical=watch.mechanical,
            cosmetic=watch.cosmetic,
            completeness=watch.completeness,
            originality=watch.originality,
            listing_quality_score=listing_quality_score,
            valuation_confidence=market.valuation_confidence,
            seller_reliability=watch.seller_reliability,
            transaction_protections=watch.transaction_protections,
        ),
        gates,
        ruleset,
    )

    return AnalysisOutcome(
        gates=gates,
        score=score,
        scenarios=scenarios,
        max_purchase=max_purchase,
        listing_price_eur=_listing_price(market, terms),
        allocation_rate=rates.allocation_rate,
        brand_concentration_rate=rates.brand_concentration_rate,
        capital_immobilization_rate=rates.capital_immobilization_rate,
    )
