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


# Échelles ordinales servant à mesurer un écart. `unknown` en est absent :
# c'est une absence de donnée, pas un degré intermédiaire.
_MECHANICAL_ORDER = ("verified", "functional", "defect")
_COSMETIC_ORDER = ("excellent", "very_good", "good", "fair", "poor")
_COMPLETENESS_ORDER = ("full_set", "box_or_papers", "watch_only")


def _ordinal_gap(
    order: tuple[str, ...], left: str | None, right: str | None
) -> int | None:
    if left not in order or right not in order:
        return None
    return abs(order.index(str(left)) - order.index(str(right)))


def condition_gap(
    comparable_condition: dict[str, object], target_condition: dict[str, object]
) -> str:
    """Classe l'écart d'état entre un comparable et la montre analysée.

    `calculation-spec.md` dit « état ±1 / ±2 / inconnu » sans préciser quelle
    dimension gouverne. L'écart le plus défavorable entre mécanique et
    cosmétique est retenu — la lecture prudente de principles.md #6 — et un
    écart supérieur à deux niveaux retombe sur `unknown`, qui porte le
    coefficient le plus bas. Choix signalé en Q-12.
    """

    gaps = [
        _ordinal_gap(
            _MECHANICAL_ORDER,
            comparable_condition.get("mechanical"),  # type: ignore[arg-type]
            target_condition.get("mechanical"),  # type: ignore[arg-type]
        ),
        _ordinal_gap(
            _COSMETIC_ORDER,
            comparable_condition.get("cosmetic"),  # type: ignore[arg-type]
            target_condition.get("cosmetic"),  # type: ignore[arg-type]
        ),
    ]

    if any(gap is None for gap in gaps):
        return "unknown"

    worst = max(gap for gap in gaps if gap is not None)
    if worst <= 1:
        return "one_level"
    if worst == 2:
        return "two_levels"
    return "unknown"


def completeness_gap(comparable_level: str | None, target_level: str | None) -> str:
    """Classe l'écart de set.

    Le ruleset ne prévoit que `same`, `one_level` et `unknown` : un écart de
    deux niveaux — montre seule face à un full set — retombe donc sur `unknown`,
    le coefficient le plus bas, plutôt que d'être assimilé à un seul niveau.
    Choix signalé en Q-12.
    """

    gap = _ordinal_gap(_COMPLETENESS_ORDER, comparable_level, target_level)
    if gap is None:
        return "unknown"
    if gap == 0:
        return "same"
    if gap == 1:
        return "one_level"
    return "unknown"


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
