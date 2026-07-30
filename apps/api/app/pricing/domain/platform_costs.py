from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from app.pricing.domain.costs import Cost, CostMode, CostPhase


@dataclass(frozen=True, slots=True)
class PlatformFees:
    """Frais figés d'une `PlatformRule`, côté acheteur et côté vendeur.

    Les deux côtés coexistent parce qu'une opération complète les traverse
    tous les deux : on achète sur une plateforme et on revend sur une autre,
    ou sur la même. Les confondre fausserait le produit net.
    """

    buyer_fee_rate: Decimal | None = None
    buyer_fee_fixed: Decimal | None = None
    buyer_fee_min: Decimal | None = None
    buyer_fee_max: Decimal | None = None

    seller_fee_rate: Decimal | None = None
    seller_fee_fixed: Decimal | None = None
    seller_fee_min: Decimal | None = None
    seller_fee_max: Decimal | None = None

    @property
    def buyer_fee_is_linear(self) -> bool:
        """Une borne rend le frais non linéaire dans le prix d'achat.

        Le prix maximal ne peut alors plus se résoudre en forme fermée : c'est
        exactement le cas que le solveur binaire prend en charge.
        """

        return self.buyer_fee_min is None and self.buyer_fee_max is None


def costs_from_platform(
    fees: PlatformFees,
    *,
    label: str,
    inbound_shipping_eur: Decimal = Decimal("0"),
    outbound_shipping_eur: Decimal = Decimal("0"),
) -> list[Cost]:
    """Traduit une règle de plateforme en coûts exploitables par le pricing.

    Les frais de plateforme sont certains : ils ne varient pas selon le
    scénario, d'où les trois valeurs identiques. Ce sont les coûts
    opérationnels — révision, polissage — qui portent l'incertitude, et ils ne
    viennent pas d'ici.

    Les frais acheteur relèvent de l'acquisition, les frais vendeur de la
    vente : la phase détermine à quel prix le taux s'applique, et les
    intervertir rendrait le calcul silencieusement faux.
    """

    costs: list[Cost] = []

    def add(
        suffix: str, mode: CostMode, phase: CostPhase, value: Decimal | None
    ) -> None:
        if value is None or value == 0:
            return
        costs.append(
            Cost(
                label=f"{label} — {suffix}",
                mode=mode,
                phase=phase,
                low=value,
                central=value,
                high=value,
            )
        )

    add("commission achat", CostMode.RATE, CostPhase.ACQUISITION, fees.buyer_fee_rate)
    add(
        "frais fixes achat", CostMode.FIXED, CostPhase.ACQUISITION, fees.buyer_fee_fixed
    )
    add("commission vente", CostMode.RATE, CostPhase.SALE, fees.seller_fee_rate)
    add("frais fixes vente", CostMode.FIXED, CostPhase.SALE, fees.seller_fee_fixed)
    add(
        "transport entrant", CostMode.FIXED, CostPhase.ACQUISITION, inbound_shipping_eur
    )
    add("transport sortant", CostMode.FIXED, CostPhase.SALE, outbound_shipping_eur)

    return costs


def buyer_cost_function(
    fees: PlatformFees, fixed_costs_eur: Decimal
) -> Callable[[Decimal], Decimal] | None:
    """Coût total prudent avant vente pour un prix d'achat donné.

    Nécessaire dès que les frais acheteur sont bornés : la forme fermée du prix
    maximal suppose une linéarité que `min`/`max` détruisent. Retourne `None`
    quand les frais sont linéaires, pour que l'appelant conserve la forme
    fermée — plus rapide et exacte.
    """

    if fees.buyer_fee_is_linear:
        return None

    rate = fees.buyer_fee_rate or Decimal("0")
    fixed_fee = fees.buyer_fee_fixed or Decimal("0")

    def cost_of_purchase(price: Decimal) -> Decimal:
        variable = price * rate
        if fees.buyer_fee_min is not None and variable < fees.buyer_fee_min:
            variable = fees.buyer_fee_min
        if fees.buyer_fee_max is not None and variable > fees.buyer_fee_max:
            variable = fees.buyer_fee_max
        return price + variable + fixed_fee + fixed_costs_eur

    return cost_of_purchase
