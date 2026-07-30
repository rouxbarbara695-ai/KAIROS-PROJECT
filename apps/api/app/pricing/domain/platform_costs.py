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

    Les taux sont ceux que la plateforme publie, jamais un taux recomposé. La
    TVA sur la commission est donc portée à part : certaines plateformes
    annoncent leurs frais taxe comprise, d'autres hors taxe en ajoutant la TVA
    à la facture. Prémultiplier le taux publié rendrait la grille
    invérifiable — on ne saurait plus, six mois plus tard, si 15 % vient de la
    page ou d'un calcul.

    Un taux de TVA à `None` signifie « non renseigné », et non « pas de
    TVA » : aucune taxe n'est alors ajoutée, mais la ligne correspondante
    n'apparaît pas dans le détail des coûts. L'absence se voit, au lieu d'être
    comblée par une valeur inventée (CLAUDE.md règle 1).

    `payment_fee_rate` couvre les frais de traitement du paiement prélevés au
    vendeur, quand la plateforme les facture en plus de sa commission. Ils ne
    portent pas de TVA : ce sont des frais financiers.
    """

    buyer_fee_rate: Decimal | None = None
    buyer_fee_fixed: Decimal | None = None
    buyer_fee_min: Decimal | None = None
    buyer_fee_max: Decimal | None = None
    buyer_fee_vat_rate: Decimal | None = None

    seller_fee_rate: Decimal | None = None
    seller_fee_fixed: Decimal | None = None
    seller_fee_min: Decimal | None = None
    seller_fee_max: Decimal | None = None
    seller_fee_vat_rate: Decimal | None = None

    payment_fee_rate: Decimal | None = None

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

    def taxed(value: Decimal | None, vat_rate: Decimal | None) -> Decimal | None:
        """La part de TVA d'un frais, ou `None` s'il n'y a rien à ajouter.

        Une ligne distincte plutôt qu'un taux majoré : le détail des coûts doit
        montrer que 12,5 % de commission coûtent 15 % à un vendeur qui ne
        récupère pas la taxe. Fondre les deux masquerait la seule ligne que
        change un changement de statut fiscal.
        """

        if value is None or vat_rate is None:
            return None
        return value * vat_rate

    add("commission achat", CostMode.RATE, CostPhase.ACQUISITION, fees.buyer_fee_rate)
    add(
        "TVA sur commission achat",
        CostMode.RATE,
        CostPhase.ACQUISITION,
        taxed(fees.buyer_fee_rate, fees.buyer_fee_vat_rate),
    )
    add(
        "frais fixes achat", CostMode.FIXED, CostPhase.ACQUISITION, fees.buyer_fee_fixed
    )
    add(
        "TVA sur frais fixes achat",
        CostMode.FIXED,
        CostPhase.ACQUISITION,
        taxed(fees.buyer_fee_fixed, fees.buyer_fee_vat_rate),
    )
    add("commission vente", CostMode.RATE, CostPhase.SALE, fees.seller_fee_rate)
    add(
        "TVA sur commission vente",
        CostMode.RATE,
        CostPhase.SALE,
        taxed(fees.seller_fee_rate, fees.seller_fee_vat_rate),
    )
    add("frais fixes vente", CostMode.FIXED, CostPhase.SALE, fees.seller_fee_fixed)
    add(
        "TVA sur frais fixes vente",
        CostMode.FIXED,
        CostPhase.SALE,
        taxed(fees.seller_fee_fixed, fees.seller_fee_vat_rate),
    )
    # Prélevés sur le prix de vente, donc au vendeur : les compter à l'achat
    # les appliquerait au mauvais montant.
    add("frais de paiement", CostMode.RATE, CostPhase.SALE, fees.payment_fee_rate)
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
    vat = Decimal("1") + (fees.buyer_fee_vat_rate or Decimal("0"))

    def cost_of_purchase(price: Decimal) -> Decimal:
        variable = price * rate
        if fees.buyer_fee_min is not None and variable < fees.buyer_fee_min:
            variable = fees.buyer_fee_min
        if fees.buyer_fee_max is not None and variable > fees.buyer_fee_max:
            variable = fees.buyer_fee_max
        # La TVA porte sur la commission telle qu'elle est facturée, donc après
        # application du plancher et du plafond : c'est le montant facturé qui
        # est taxé, pas le montant théorique.
        return price + (variable + fixed_fee) * vat + fixed_costs_eur

    return cost_of_purchase
