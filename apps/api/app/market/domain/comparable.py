from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.rules.ruleset import Ruleset

# Précision de travail : la spec impose au moins 8 décimales en interne et
# n'arrondit qu'aux sorties monétaires (calculation-spec.md § en-tête).
_INTERNAL = Decimal("0.00000001")
_MONETARY = Decimal("0.01")

_SET_PREMIUM = ("comparable", "set_premium")
_SOURCE_RELIABILITY = ("comparable", "source_reliability")
_REFERENCE = ("comparable", "reference")
_CONDITION = ("comparable", "condition")
_COMPLETENESS = ("comparable", "completeness")
_SELLER_INDEPENDENCE = ("comparable", "seller_independence")
_RECENCY = ("comparable", "recency")


def _quantize_internal(value: Decimal) -> Decimal:
    return value.quantize(_INTERNAL, rounding=ROUND_HALF_UP)


def round_monetary(value: Decimal) -> Decimal:
    return value.quantize(_MONETARY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class BuyerFeeRule:
    """Grille de frais acheteur, telle que figée dans une `PlatformRule`.

    Une borne à `None` signifie absence de borne (calculation-spec.md § 2).
    """

    rate: Decimal | None = None
    fixed: Decimal | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None


@dataclass(frozen=True, slots=True)
class BuyerCost:
    base_price_eur: Decimal
    variable_fee_eur: Decimal
    fixed_fee_eur: Decimal
    shipping_eur: Decimal
    total_eur: Decimal


def buyer_total_price(
    base_price_eur: Decimal,
    rule: BuyerFeeRule,
    compulsory_shipping_not_included_eur: Decimal = Decimal("0"),
) -> BuyerCost:
    """Prix total réellement payé par l'acheteur pour obtenir la montre.

    Les frais vendeur ne sont jamais retranchés ici : ils ne servent qu'au
    produit net d'une vente de l'utilisateur (calculation-spec.md § 2).
    """

    if base_price_eur < 0:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Le prix de base ne peut pas être négatif.",
            field="base_price_eur",
        )

    rate = rule.rate if rule.rate is not None else Decimal("0")
    variable = _quantize_internal(base_price_eur * rate)

    # `clamp` n'est appliqué qu'à la part variable, et seulement du côté où une
    # borne existe.
    if rule.minimum is not None and variable < rule.minimum:
        variable = rule.minimum
    if rule.maximum is not None and variable > rule.maximum:
        variable = rule.maximum

    fixed = rule.fixed if rule.fixed is not None else Decimal("0")
    shipping = compulsory_shipping_not_included_eur

    total = base_price_eur + variable + fixed + shipping

    return BuyerCost(
        base_price_eur=round_monetary(base_price_eur),
        variable_fee_eur=round_monetary(variable),
        fixed_fee_eur=round_monetary(fixed),
        shipping_eur=round_monetary(shipping),
        total_eur=round_monetary(total),
    )


def adjust_for_set(
    buyer_total_price_eur: Decimal,
    comparable_completeness: str,
    target_completeness: str,
    ruleset: Ruleset,
) -> Decimal:
    """Ramène un comparable au set de la montre analysée.

    Le prix est d'abord ramené à une montre seule, puis reporté vers le set
    cible — les primes ne se cumulent donc jamais au-delà de leur barème.
    """

    comparable_premium = ruleset.decimal_in(_SET_PREMIUM, comparable_completeness)
    target_premium = ruleset.decimal_in(_SET_PREMIUM, target_completeness)

    watch_only_price = buyer_total_price_eur / (Decimal("1") + comparable_premium)
    adjusted = watch_only_price * (Decimal("1") + target_premium)

    return round_monetary(adjusted)


def recency_factor(age_days: int, ruleset: Ruleset) -> Decimal:
    """Coefficient de fraîcheur par tranche d'âge.

    Les bornes sont inclusives et ordonnées : la première tranche atteinte
    l'emporte, ce qui rend le classement déterministe aux jonctions (30, 90…).
    """

    if age_days < 0:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "L'âge d'un comparable ne peut pas être négatif.",
            field="age_days",
        )

    for limit, key in (
        (30, "days_30"),
        (90, "days_90"),
        (180, "days_180"),
        (365, "days_365"),
    ):
        if age_days <= limit:
            return ruleset.decimal(*_RECENCY, key)
    return ruleset.decimal(*_RECENCY, "older")


@dataclass(frozen=True, slots=True)
class WeightFactors:
    source_reliability: Decimal
    recency: Decimal
    reference_similarity: Decimal
    condition_similarity: Decimal
    completeness_similarity: Decimal
    seller_independence: Decimal

    @property
    def weight(self) -> Decimal:
        return _quantize_internal(
            self.source_reliability
            * self.recency
            * self.reference_similarity
            * self.condition_similarity
            * self.completeness_similarity
            * self.seller_independence
        )


def comparable_weight(
    *,
    reliability_class: str,
    age_days: int,
    reference_match: str,
    condition_gap: str,
    completeness_gap: str,
    seller_relation: str,
    ruleset: Ruleset,
) -> WeightFactors:
    """Poids d'un comparable, facteur par facteur.

    La fiabilité de source n'entre qu'une seule fois dans le produit
    (calculation-spec.md § 2) : elle décrit la qualité de la preuve, tandis que
    `price_kind` en décrit la nature économique, sans se substituer à elle.

    Une référence classée « autre » est exclue en amont plutôt que pondérée :
    le ruleset ne lui attribue volontairement aucun coefficient.
    """

    if reference_match not in ruleset.mapping(*_REFERENCE):
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Un comparable dont la référence ne correspond pas doit être exclu, "
            "pas pondéré.",
            field="reference_match",
            details={"reference_match": reference_match},
        )

    return WeightFactors(
        source_reliability=ruleset.decimal_in(_SOURCE_RELIABILITY, reliability_class),
        recency=recency_factor(age_days, ruleset),
        reference_similarity=ruleset.decimal_in(_REFERENCE, reference_match),
        condition_similarity=ruleset.decimal_in(_CONDITION, condition_gap),
        completeness_similarity=ruleset.decimal_in(_COMPLETENESS, completeness_gap),
        seller_independence=ruleset.decimal_in(_SELLER_INDEPENDENCE, seller_relation),
    )
