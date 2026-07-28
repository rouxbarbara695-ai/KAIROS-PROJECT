from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.market.domain.valuation import MarketQuote
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.rules.ruleset import Ruleset

_CONFIDENCE = ("valuation_confidence",)
_WEIGHTS = ("valuation_confidence", "weights")
_VOLUME = ("valuation_confidence", "volume_scores")
_DISPERSION = ("valuation_confidence", "dispersion_scores")
_CAPS = ("valuation_confidence", "caps")
_RELIABILITY = ("comparable", "source_reliability")

_PRECISION = Decimal("0.01")
_HUNDRED = Decimal("100")

# Classes considérées comme preuve forte pour le plafond « aucun A/B ».
_STRONG_CLASSES = frozenset({"a", "b"})


@dataclass(frozen=True, slots=True)
class ConfidenceInput:
    """Un comparable retenu, vu par l'indice de confiance.

    Les facteurs sont repris bruts et non le poids final : réutiliser ce
    dernier recompterait la fiabilité de source et la récence à l'intérieur de
    leur propre sous-score (calculation-spec.md § 3).
    """

    reliability_class: str
    recency_factor: Decimal
    reference_similarity: Decimal
    condition_similarity: Decimal
    completeness_similarity: Decimal
    seller_key: str


@dataclass(frozen=True, slots=True)
class AppliedCap:
    name: str
    value: Decimal
    reason: str


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    """Indice de confiance et sa trace.

    La trace expose les composantes, les plafonds retenus et la version du
    ruleset, comme l'exige la règle 6 : une recommandation doit pouvoir être
    rejouée et contestée à partir de ce qu'elle publie.
    """

    value: Decimal
    uncapped_value: Decimal
    volume_score: Decimal
    source_reliability_score: Decimal
    recency_score: Decimal
    similarity_score: Decimal
    dispersion_score: Decimal
    applied_caps: tuple[AppliedCap, ...]
    ruleset_version: str


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _volume_score(count: int, ruleset: Ruleset) -> Decimal:
    if count >= 8:
        return ruleset.decimal(*_VOLUME, "8_plus")
    if count >= 5:
        return ruleset.decimal(*_VOLUME, "5_7")
    # En deçà de 5, le barème est indexé par l'effectif exact. Un effectif hors
    # barème signale une précondition non tenue en amont, pas un défaut à lisser.
    return ruleset.decimal_in(_VOLUME, str(count))


def _dispersion_score(quote: MarketQuote, ruleset: Ruleset) -> Decimal:
    if quote.central_eur <= 0:
        raise DomainError(
            ErrorCode.VALUATION_INSUFFICIENT_COMPARABLES,
            "Une cote centrale nulle ou négative rend la dispersion indéfinie.",
        )

    width_ratio = (quote.high_eur - quote.low_eur) / quote.central_eur

    for limit, key in (
        (Decimal("0.10"), "width_10"),
        (Decimal("0.20"), "width_20"),
        (Decimal("0.30"), "width_30"),
        (Decimal("0.45"), "width_45"),
    ):
        if width_ratio <= limit:
            return ruleset.decimal(*_DISPERSION, key)
    return ruleset.decimal(*_DISPERSION, "wider")


def valuation_confidence(
    comparables: list[ConfidenceInput],
    quote: MarketQuote,
    *,
    identity_confirmed: bool,
    ruleset: Ruleset,
) -> ConfidenceResult:
    """Indice de confiance /100 et sa trace.

    Les plafonds sont tous conservés, pas seulement le dernier applicable : le
    résultat retient donc le plus contraignant, et la trace liste chacun d'eux
    avec son motif (calculation-spec.md § 3).
    """

    if not comparables:
        raise DomainError(
            ErrorCode.VALUATION_INSUFFICIENT_COMPARABLES,
            "Aucun comparable retenu pour calculer la confiance.",
        )

    volume = _volume_score(len(comparables), ruleset)

    # A=100, B=85… reprennent le barème de fiabilité déjà porté par le ruleset,
    # multiplié par cent : deux tables distinctes pourraient diverger.
    reliability = _mean(
        [
            ruleset.decimal_in(_RELIABILITY, item.reliability_class) * _HUNDRED
            for item in comparables
        ]
    )
    recency = _mean([item.recency_factor * _HUNDRED for item in comparables])
    similarity = _mean(
        [
            item.reference_similarity
            * item.condition_similarity
            * item.completeness_similarity
            * _HUNDRED
            for item in comparables
        ]
    )
    dispersion = _dispersion_score(quote, ruleset)

    uncapped = (
        volume * ruleset.decimal(*_WEIGHTS, "volume")
        + reliability * ruleset.decimal(*_WEIGHTS, "source_reliability")
        + recency * ruleset.decimal(*_WEIGHTS, "recency")
        + similarity * ruleset.decimal(*_WEIGHTS, "similarity")
        + dispersion * ruleset.decimal(*_WEIGHTS, "dispersion")
    )

    caps: list[AppliedCap] = []

    if not any(item.reliability_class in _STRONG_CLASSES for item in comparables):
        caps.append(
            AppliedCap(
                name="no_ab",
                value=ruleset.decimal(*_CAPS, "no_ab"),
                reason="Aucun comparable de classe A ou B.",
            )
        )

    if len(comparables) == 2:
        caps.append(
            AppliedCap(
                name="two_comparables",
                value=ruleset.decimal(*_CAPS, "two_comparables"),
                reason="Seulement deux comparables retenus.",
            )
        )

    if not identity_confirmed:
        caps.append(
            AppliedCap(
                name="identity_unconfirmed",
                value=ruleset.decimal(*_CAPS, "identity_unconfirmed"),
                reason="Référence de la montre non confirmée.",
            )
        )

    if len({item.seller_key for item in comparables}) == 1:
        caps.append(
            AppliedCap(
                name="single_seller",
                value=ruleset.decimal(*_CAPS, "single_seller"),
                reason="Tous les comparables proviennent d'un même vendeur.",
            )
        )

    value = uncapped
    for cap in caps:
        value = min(value, cap.value)

    return ConfidenceResult(
        value=value.quantize(_PRECISION, rounding=ROUND_HALF_UP),
        uncapped_value=uncapped.quantize(_PRECISION, rounding=ROUND_HALF_UP),
        volume_score=volume,
        source_reliability_score=reliability.quantize(
            _PRECISION, rounding=ROUND_HALF_UP
        ),
        recency_score=recency.quantize(_PRECISION, rounding=ROUND_HALF_UP),
        similarity_score=similarity.quantize(_PRECISION, rounding=ROUND_HALF_UP),
        dispersion_score=dispersion,
        applied_caps=tuple(caps),
        ruleset_version=ruleset.version,
    )
