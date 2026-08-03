from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.pricing.domain.costs import Cost, CostMode, CostPhase
from app.shared.domain.errors import DomainError, ErrorCode

_MONETARY = Decimal("0.01")


class FeeBasis(StrEnum):
    """Sur quoi la commission se calcule.

    eBay prélève sur le montant total payé par l'acheteur, frais de port
    compris ; Chrono24 sur le seul prix de la montre. Sur une vente à 3 600 €
    avec 20 € de port, l'écart n'est que de 2 € — mais il est systématique, et
    supposer une base au lieu de la lire reviendrait à inventer une règle.
    """

    PRICE = "price"
    PRICE_AND_SHIPPING = "price_and_shipping"


@dataclass(frozen=True, slots=True)
class FeeTier:
    """Une tranche de barème, appliquée **marginalement**.

    « 10 % jusqu'à 2 000 € puis 2 % au-delà » ne veut pas dire que tout bascule
    à 2 % au-dessus de 2 000 € : les 2 000 premiers euros restent à 10 %, comme
    un barème d'imposition. Confondre les deux lectures se paie cher — sur une
    vente à 10 000 €, 360 € de commission réelle contre 200 € pour la lecture
    à seuil.
    """

    up_to: Decimal | None
    rate: Decimal


def _tiered_amount(base: Decimal, tiers: tuple[FeeTier, ...]) -> Decimal:
    """Applique un barème par tranches, marginalement."""

    total = Decimal("0")
    floor = Decimal("0")
    for tier in tiers:
        if tier.up_to is not None and base <= tier.up_to:
            total += (base - floor) * tier.rate
            return total
        ceiling = base if tier.up_to is None else tier.up_to
        total += (ceiling - floor) * tier.rate
        floor = ceiling
        if tier.up_to is None:
            return total

    # Dernière tranche bornée et montant au-delà : le barème est incomplet.
    # Extrapoler au dernier taux serait une invention (CLAUDE.md règle 1).
    if base > floor:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            f"Le barème ne couvre pas les montants au-delà de {floor} €. "
            "Ajouter une tranche finale sans plafond.",
            field="fee_tiers",
        )
    return total


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

    Un barème par tranches, quand il existe, remplace le taux unique. Les deux
    ne se cumulent jamais : `commission` ignore le taux dès qu'il y a des
    tranches.
    """

    buyer_fee_rate: Decimal | None = None
    buyer_fee_fixed: Decimal | None = None
    buyer_fee_min: Decimal | None = None
    buyer_fee_max: Decimal | None = None
    buyer_fee_vat_rate: Decimal | None = None
    buyer_fee_tiers: tuple[FeeTier, ...] = ()
    buyer_fee_basis: FeeBasis = FeeBasis.PRICE

    seller_fee_rate: Decimal | None = None
    seller_fee_fixed: Decimal | None = None
    seller_fee_min: Decimal | None = None
    seller_fee_max: Decimal | None = None
    seller_fee_vat_rate: Decimal | None = None
    seller_fee_tiers: tuple[FeeTier, ...] = ()
    seller_fee_basis: FeeBasis = FeeBasis.PRICE

    payment_fee_rate: Decimal | None = None

    @property
    def has_buyer_fees(self) -> bool:
        return any(
            (
                self.buyer_fee_rate,
                self.buyer_fee_fixed,
                self.buyer_fee_min,
                self.buyer_fee_max,
                self.buyer_fee_tiers,
            )
        )


@dataclass(frozen=True, slots=True)
class CommissionBreakdown:
    """Ce qu'une commission coûte, décomposé pour rester explicable.

    La règle 6 exige que toute recommandation expose ses entrées et ses
    calculs. Un montant unique dirait combien, jamais pourquoi.
    """

    variable: Decimal
    fixed: Decimal
    vat: Decimal
    applied_floor: bool = False
    applied_cap: bool = False

    @property
    def total(self) -> Decimal:
        return self.variable + self.fixed + self.vat


def commission(
    base: Decimal,
    *,
    rate: Decimal | None,
    tiers: tuple[FeeTier, ...],
    fixed: Decimal | None,
    minimum: Decimal | None,
    maximum: Decimal | None,
    vat_rate: Decimal | None,
) -> CommissionBreakdown:
    """La commission réellement facturée sur un montant donné.

    Le plancher et le plafond s'appliquent à la part variable, pas au frais
    fixe : une plateforme qui annonce « commission plafonnée à 500 € » ne
    renonce pas à ses frais de dossier. La TVA porte ensuite sur le montant
    facturé, donc après bornage — c'est ce qui est facturé qui est taxé, pas ce
    qui aurait été dû sans plafond.
    """

    variable = _tiered_amount(base, tiers) if tiers else base * (rate or Decimal("0"))

    applied_floor = minimum is not None and variable < minimum
    if applied_floor and minimum is not None:
        variable = minimum
    applied_cap = maximum is not None and variable > maximum
    if applied_cap and maximum is not None:
        variable = maximum

    fixed_fee = fixed or Decimal("0")
    vat = (variable + fixed_fee) * (vat_rate or Decimal("0"))

    return CommissionBreakdown(
        variable=variable.quantize(_MONETARY, rounding=ROUND_HALF_UP),
        fixed=fixed_fee.quantize(_MONETARY, rounding=ROUND_HALF_UP),
        vat=vat.quantize(_MONETARY, rounding=ROUND_HALF_UP),
        applied_floor=applied_floor,
        applied_cap=applied_cap,
    )


def buyer_commission(
    fees: PlatformFees, purchase_price_eur: Decimal, inbound_shipping_eur: Decimal
) -> CommissionBreakdown:
    base = purchase_price_eur
    if fees.buyer_fee_basis is FeeBasis.PRICE_AND_SHIPPING:
        base += inbound_shipping_eur
    return commission(
        base,
        rate=fees.buyer_fee_rate,
        tiers=fees.buyer_fee_tiers,
        fixed=fees.buyer_fee_fixed,
        minimum=fees.buyer_fee_min,
        maximum=fees.buyer_fee_max,
        vat_rate=fees.buyer_fee_vat_rate,
    )


def seller_commission(
    fees: PlatformFees, sale_price_eur: Decimal, outbound_shipping_eur: Decimal
) -> CommissionBreakdown:
    base = sale_price_eur
    if fees.seller_fee_basis is FeeBasis.PRICE_AND_SHIPPING:
        base += outbound_shipping_eur
    return commission(
        base,
        rate=fees.seller_fee_rate,
        tiers=fees.seller_fee_tiers,
        fixed=fees.seller_fee_fixed,
        minimum=fees.seller_fee_min,
        maximum=fees.seller_fee_max,
        vat_rate=fees.seller_fee_vat_rate,
    )


@dataclass(frozen=True, slots=True)
class PriceContext:
    """Les prix connus au moment d'établir les coûts d'un scénario.

    Les commissions se calculent désormais **au montant**, jamais au taux :
    c'est la seule façon d'honorer un barème par tranches, un plancher ou un
    plafond. Il faut donc connaître les prix, et ils diffèrent d'un scénario à
    l'autre — d'où ce contexte plutôt qu'un calcul unique valable pour les
    trois.
    """

    purchase_price_eur: Decimal
    sale_price_eur: Decimal
    inbound_shipping_eur: Decimal = Decimal("0")
    outbound_shipping_eur: Decimal = Decimal("0")
    operational_before_sale_eur: Decimal = field(default=Decimal("0"))


def costs_from_platform(
    fees: PlatformFees,
    *,
    label: str,
    prices: PriceContext,
) -> list[Cost]:
    """Traduit une règle de plateforme en coûts exploitables par le pricing.

    Les frais de plateforme sont certains : ils ne varient pas selon le
    scénario **à prix donné**, d'où les trois valeurs identiques. Ce sont les
    coûts opérationnels — révision, polissage — qui portent l'incertitude, et
    ils ne viennent pas d'ici.

    Tout est émis en montant fixe, y compris les commissions proportionnelles.
    C'est ce qui permet d'honorer tranches, planchers et plafonds : un taux
    unique ne sait représenter aucun des trois. Le prix de chaque scénario
    étant connu, il n'y a rien à approximer.
    """

    costs: list[Cost] = []

    def add(suffix: str, phase: CostPhase, value: Decimal | None) -> None:
        if value is None or value == 0:
            return
        costs.append(
            Cost(
                label=f"{label} — {suffix}",
                mode=CostMode.FIXED,
                phase=phase,
                low=value,
                central=value,
                high=value,
            )
        )

    buyer = buyer_commission(
        fees, prices.purchase_price_eur, prices.inbound_shipping_eur
    )
    add("commission achat", CostPhase.ACQUISITION, buyer.variable)
    add("frais fixes achat", CostPhase.ACQUISITION, buyer.fixed)
    add("TVA sur frais d'achat", CostPhase.ACQUISITION, buyer.vat)

    seller = seller_commission(
        fees, prices.sale_price_eur, prices.outbound_shipping_eur
    )
    add("commission vente", CostPhase.SALE, seller.variable)
    add("frais fixes vente", CostPhase.SALE, seller.fixed)
    add("TVA sur frais de vente", CostPhase.SALE, seller.vat)

    # Prélevés sur le prix de vente, donc au vendeur : les compter à l'achat
    # les appliquerait au mauvais montant. Pas de TVA — frais financiers.
    if fees.payment_fee_rate:
        add(
            "frais de paiement",
            CostPhase.SALE,
            (prices.sale_price_eur * fees.payment_fee_rate).quantize(
                _MONETARY, rounding=ROUND_HALF_UP
            ),
        )

    add("transport entrant", CostPhase.ACQUISITION, prices.inbound_shipping_eur)
    add("transport sortant", CostPhase.SALE, prices.outbound_shipping_eur)

    return costs


def buyer_cost_function(
    fees: PlatformFees, fixed_costs_eur: Decimal, inbound_shipping_eur: Decimal
) -> Callable[[Decimal], Decimal] | None:
    """Coût total prudent avant vente pour un prix d'achat donné.

    Retourne `None` quand la plateforme ne prélève rien à l'achat : le prix
    maximal se résout alors en forme fermée, plus rapide et exacte.

    Dès qu'il existe le moindre frais acheteur, c'est cette fonction qui fait
    foi. On ne tente plus de deviner si les frais sont « linéaires » : un
    barème par tranches, un plancher ou un plafond les rendent non linéaires,
    et une seule implémentation du coût vaut mieux que deux qui pourraient
    diverger.
    """

    if not fees.has_buyer_fees:
        return None

    def cost_of_purchase(price: Decimal) -> Decimal:
        fee = buyer_commission(fees, price, inbound_shipping_eur)
        return price + fee.total + fixed_costs_eur

    return cost_of_purchase
