from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from app.pricing.domain.costs import Cost, Scenario, summarise_costs
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.rules.ruleset import Ruleset

_MONETARY = Decimal("0.01")
_PRICING = ("pricing",)
_ROUNDING = ("pricing", "purchase_rounding")

# Le solveur travaille au centime : chercher plus fin n'aurait aucun sens
# monétaire et rallongerait la recherche sans rien changer au résultat arrondi.
_SOLVER_PRECISION = Decimal("0.01")
_MAX_ITERATIONS = 64


@dataclass(frozen=True, slots=True)
class MaxPurchasePrice:
    """Prix maximal d'achat et sa trace.

    `raw_value_eur` conserve la valeur avant arrondi : l'écart avec la valeur
    retenue doit rester lisible, et l'arrondi se fait toujours vers le bas —
    jamais vers un prix qu'on ne pourrait pas défendre.
    """

    value_eur: Decimal
    raw_value_eur: Decimal
    increment_eur: Decimal
    binding_constraint: str
    solver: str
    iterations: int


def _rounding_increment(raw: Decimal, ruleset: Ruleset) -> Decimal:
    if raw < Decimal("2000"):
        return ruleset.decimal(*_ROUNDING, "under_2000")
    if raw <= Decimal("5000"):
        return ruleset.decimal(*_ROUNDING, "from_2000_to_5000")
    return ruleset.decimal(*_ROUNDING, "over_5000")


def _round_down_to_increment(raw: Decimal, increment: Decimal) -> Decimal:
    if increment <= 0:
        raise DomainError(
            ErrorCode.RULESET_MISSING,
            "L'incrément d'arrondi doit être strictement positif.",
        )
    return (raw / increment).to_integral_value(rounding=ROUND_DOWN) * increment


def max_purchase_price(
    *,
    net_sale_proceeds_eur: Decimal,
    prudent_costs: list[Cost],
    minimum_profit_eur: Decimal,
    minimum_roi: Decimal,
    ruleset: Ruleset,
    cost_of_purchase: Callable[[Decimal], Decimal] | None = None,
) -> MaxPurchasePrice:
    """Prix d'achat maximal, calculé sur le seul scénario prudent.

    Aucune négociation supposée n'y entre : le maximum est ce qu'on peut payer
    en tenant ses propres contraintes, pas ce qu'on espère obtenir en
    discutant (calculation-spec.md § 6).

    La forme fermée n'est valable que si tous les coûts dépendant du prix
    d'achat sont linéaires. Dès qu'une grille comporte un minimum, un maximum
    ou un palier, elle cesse de l'être et le calcul bascule sur une recherche
    binaire — d'où `cost_of_purchase`, qui décrit alors le coût réel.
    """

    breakdown = summarise_costs(prudent_costs, Scenario.PRUDENT)
    net = net_sale_proceeds_eur
    fixed = breakdown.fixed_costs_before_sale
    rate = breakdown.purchase_variable_rate

    if cost_of_purchase is None:
        return _closed_form(
            net=net,
            fixed=fixed,
            rate=rate,
            minimum_profit_eur=minimum_profit_eur,
            minimum_roi=minimum_roi,
            ruleset=ruleset,
        )

    return _binary_search(
        net=net,
        cost_of_purchase=cost_of_purchase,
        minimum_profit_eur=minimum_profit_eur,
        minimum_roi=minimum_roi,
        ruleset=ruleset,
    )


def _closed_form(
    *,
    net: Decimal,
    fixed: Decimal,
    rate: Decimal,
    minimum_profit_eur: Decimal,
    minimum_roi: Decimal,
    ruleset: Ruleset,
) -> MaxPurchasePrice:
    divisor = Decimal("1") + rate
    max_by_profit = (net - fixed - minimum_profit_eur) / divisor
    max_by_roi = (net / (Decimal("1") + minimum_roi) - fixed) / divisor

    binding = "profit" if max_by_profit <= max_by_roi else "roi"
    raw = max(Decimal("0"), min(max_by_profit, max_by_roi))
    raw = raw.quantize(_MONETARY, rounding=ROUND_HALF_UP)

    increment = _rounding_increment(raw, ruleset)
    return MaxPurchasePrice(
        value_eur=_round_down_to_increment(raw, increment),
        raw_value_eur=raw,
        increment_eur=increment,
        binding_constraint=binding,
        solver="closed_form",
        iterations=0,
    )


def _binary_search(
    *,
    net: Decimal,
    cost_of_purchase: Callable[[Decimal], Decimal],
    minimum_profit_eur: Decimal,
    minimum_roi: Decimal,
    ruleset: Ruleset,
) -> MaxPurchasePrice:
    def satisfies(price: Decimal) -> bool:
        total_cost = cost_of_purchase(price)
        if net - total_cost < minimum_profit_eur:
            return False
        if total_cost <= 0:
            # Sans coût, le ROI est indéfini : la contrainte de ROI ne peut pas
            # être vérifiée, donc elle ne peut pas être déclarée tenue.
            return False
        return (net - total_cost) / total_cost >= minimum_roi

    low = Decimal("0")
    high = ruleset.decimal(*_PRICING, "maximum_solver_ceiling_eur")

    if not satisfies(low):
        increment = _rounding_increment(Decimal("0"), ruleset)
        return MaxPurchasePrice(
            value_eur=Decimal("0"),
            raw_value_eur=Decimal("0"),
            increment_eur=increment,
            binding_constraint="infeasible",
            solver="binary_search",
            iterations=0,
        )

    iterations = 0
    while high - low > _SOLVER_PRECISION and iterations < _MAX_ITERATIONS:
        iterations += 1
        middle = ((low + high) / Decimal("2")).quantize(_MONETARY)
        if satisfies(middle):
            low = middle
        else:
            high = middle

    raw = low.quantize(_MONETARY, rounding=ROUND_HALF_UP)
    total_cost = cost_of_purchase(raw)
    profit_margin = net - total_cost - minimum_profit_eur
    roi_margin = (
        (net - total_cost) / total_cost - minimum_roi
        if total_cost > 0
        else Decimal("0")
    )
    binding = "profit" if profit_margin <= roi_margin else "roi"

    increment = _rounding_increment(raw, ruleset)
    return MaxPurchasePrice(
        value_eur=_round_down_to_increment(raw, increment),
        raw_value_eur=raw,
        increment_eur=increment,
        binding_constraint=binding,
        solver="binary_search",
        iterations=iterations,
    )
