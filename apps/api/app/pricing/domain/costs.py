from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.shared.domain.errors import DomainError, ErrorCode

_MONETARY = Decimal("0.01")
_RATE = Decimal("0.00000001")


class CostMode(StrEnum):
    FIXED = "fixed"
    RATE = "rate"


class CostPhase(StrEnum):
    ACQUISITION = "acquisition"
    PREPARATION = "preparation"
    SALE = "sale"


class Scenario(StrEnum):
    """Les trois scénarios de la spécification.

    Ils ne diffèrent pas seulement par le prix de vente : le prudent cumule
    vente basse **et** coûts hauts, le favorable vente haute **et** coûts bas.
    Mélanger les deux axes produirait un optimisme trompeur.
    """

    PRUDENT = "prudent"
    CENTRAL = "central"
    FAVORABLE = "favorable"


@dataclass(frozen=True, slots=True)
class Cost:
    """Un coût, décliné en trois valeurs.

    `low`, `central` et `high` décrivent l'incertitude sur le coût lui-même,
    indépendamment du scénario : c'est le scénario qui choisit laquelle
    retenir.
    """

    label: str
    mode: CostMode
    phase: CostPhase
    low: Decimal
    central: Decimal
    high: Decimal

    def value_for(self, scenario: Scenario) -> Decimal:
        if scenario is Scenario.PRUDENT:
            return self.high
        if scenario is Scenario.FAVORABLE:
            return self.low
        return self.central


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_MONETARY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    purchase_variable_rate: Decimal
    fixed_costs_before_sale: Decimal
    sale_variable_rate: Decimal
    fixed_sale_costs: Decimal


def summarise_costs(costs: list[Cost], scenario: Scenario) -> CostBreakdown:
    """Agrège les coûts d'un scénario, en séparant ce qui dépend du prix
    d'achat, ce qui dépend du prix de vente, et ce qui est fixe."""

    purchase_rate = Decimal("0")
    fixed_before_sale = Decimal("0")
    sale_rate = Decimal("0")
    fixed_sale = Decimal("0")

    for cost in costs:
        value = cost.value_for(scenario)
        if value < 0:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                f"Le coût « {cost.label} » ne peut pas être négatif.",
                field="costs",
            )

        is_sale = cost.phase is CostPhase.SALE
        if cost.mode is CostMode.RATE:
            if is_sale:
                sale_rate += value
            else:
                purchase_rate += value
        else:
            if is_sale:
                fixed_sale += value
            else:
                fixed_before_sale += value

    return CostBreakdown(
        purchase_variable_rate=purchase_rate.quantize(_RATE),
        fixed_costs_before_sale=_round_money(fixed_before_sale),
        sale_variable_rate=sale_rate.quantize(_RATE),
        fixed_sale_costs=_round_money(fixed_sale),
    )


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario: Scenario
    purchase_price_eur: Decimal
    sale_price_eur: Decimal
    total_cost_before_sale_eur: Decimal
    net_sale_proceeds_eur: Decimal
    net_profit_eur: Decimal
    roi: Decimal | None
    roi_undefined_reason: str | None


def evaluate_scenario(
    *,
    scenario: Scenario,
    purchase_price_eur: Decimal,
    sale_price_eur: Decimal,
    costs: list[Cost],
) -> ScenarioResult:
    """Profit net et ROI d'un scénario (calculation-spec.md § 5)."""

    breakdown = summarise_costs(costs, scenario)

    total_cost = _round_money(
        purchase_price_eur * (Decimal("1") + breakdown.purchase_variable_rate)
        + breakdown.fixed_costs_before_sale
    )
    sale_variable = _round_money(sale_price_eur * breakdown.sale_variable_rate)
    net_proceeds = _round_money(
        sale_price_eur - sale_variable - breakdown.fixed_sale_costs
    )
    net_profit = _round_money(net_proceeds - total_cost)

    # Un ROI sur un coût nul serait infini, pas « excellent » : la spec impose
    # de le déclarer indéfini plutôt que de produire un nombre trompeur.
    if total_cost == 0:
        return ScenarioResult(
            scenario=scenario,
            purchase_price_eur=_round_money(purchase_price_eur),
            sale_price_eur=_round_money(sale_price_eur),
            total_cost_before_sale_eur=total_cost,
            net_sale_proceeds_eur=net_proceeds,
            net_profit_eur=net_profit,
            roi=None,
            roi_undefined_reason="ROI_UNDEFINED_ZERO_COST",
        )

    return ScenarioResult(
        scenario=scenario,
        purchase_price_eur=_round_money(purchase_price_eur),
        sale_price_eur=_round_money(sale_price_eur),
        total_cost_before_sale_eur=total_cost,
        net_sale_proceeds_eur=net_proceeds,
        net_profit_eur=net_profit,
        roi=(net_profit / total_cost).quantize(_RATE),
        roi_undefined_reason=None,
    )
