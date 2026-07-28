from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.market.domain.comparable import round_monetary
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.rules.ruleset import Ruleset

_OUTLIER = ("comparable", "outlier")
_GATES = ("gates",)


def median(values: list[Decimal]) -> Decimal:
    """Médiane non pondérée. Pour un effectif pair, moyenne des deux valeurs
    centrales — convention retenue également pour les quartiles."""

    if not values:
        raise DomainError(ErrorCode.VALIDATION_ERROR, "Médiane d'un ensemble vide.")

    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _quartiles(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Q1 et Q3 selon les charnières de Tukey : médiane de chaque moitié, la
    valeur centrale étant écartée quand l'effectif est impair.

    `calculation-spec.md` ne fixe pas la méthode de quantile ; celle-ci est
    retenue parce qu'elle prolonge la médiane déjà spécifiée sans introduire
    d'interpolation. Le choix est signalé dans `open-questions.md` (Q-11) car
    il peut changer le résultat dans le repli IQR.
    """

    ordered = sorted(values)
    middle = len(ordered) // 2
    lower = ordered[:middle]
    upper = ordered[middle + 1 :] if len(ordered) % 2 == 1 else ordered[middle:]
    return median(lower), median(upper)


@dataclass(frozen=True, slots=True)
class OutlierReport:
    """Signalement d'anomalie. Un signal exclut par défaut de la valorisation
    mais ne supprime jamais le comparable : la réintégration est une décision
    auditée (calculation-spec.md § 2)."""

    flagged: tuple[bool, ...]
    method: str
    median: Decimal | None
    mad: Decimal | None
    iqr: Decimal | None

    @property
    def flagged_count(self) -> int:
        return sum(self.flagged)


def detect_outliers(prices: list[Decimal], ruleset: Ruleset) -> OutlierReport:
    """Détecte les anomalies sur les prix ajustés.

    En dessous du seuil d'effectif, aucune exclusion automatique : sur un
    échantillon réduit, un prix atypique est plus probablement une donnée rare
    qu'une erreur, et l'exclure appauvrirait une base déjà mince.
    """

    minimum_count = ruleset.integer(*_OUTLIER, "minimum_count")
    if len(prices) < minimum_count:
        return OutlierReport(
            flagged=tuple(False for _ in prices),
            method="not_applicable",
            median=None,
            mad=None,
            iqr=None,
        )

    center = median(prices)
    deviations = [abs(price - center) for price in prices]
    mad = median(deviations)

    if mad > 0:
        scale = ruleset.decimal(*_OUTLIER, "mad_scale")
        threshold = ruleset.decimal(*_OUTLIER, "modified_z_threshold")
        flagged = tuple(
            (deviation / (scale * mad)) > threshold for deviation in deviations
        )
        return OutlierReport(
            flagged=flagged, method="modified_z", median=center, mad=mad, iqr=None
        )

    # MAD nul : plus de la moitié des prix sont identiques à la médiane. Le
    # score modifié diviserait par zéro, d'où le repli sur l'écart interquartile.
    q1, q3 = _quartiles(prices)
    iqr = q3 - q1

    if iqr == 0:
        return OutlierReport(
            flagged=tuple(False for _ in prices),
            method="degenerate",
            median=center,
            mad=mad,
            iqr=iqr,
        )

    multiplier = ruleset.decimal(*_OUTLIER, "iqr_multiplier")
    low_bound = q1 - multiplier * iqr
    high_bound = q3 + multiplier * iqr
    flagged = tuple(price < low_bound or price > high_bound for price in prices)

    return OutlierReport(flagged=flagged, method="iqr", median=center, mad=mad, iqr=iqr)


@dataclass(frozen=True, slots=True)
class WeightedPrice:
    adjusted_price_eur: Decimal
    weight: Decimal


def weighted_percentile(samples: list[WeightedPrice], percentile: Decimal) -> Decimal:
    """Premier prix dont le poids cumulé atteint `percentile × poids_total`,
    les prix étant triés par ordre croissant (calculation-spec.md § 3)."""

    if not samples:
        raise DomainError(
            ErrorCode.VALUATION_INSUFFICIENT_COMPARABLES,
            "Aucun comparable recevable pour calculer un percentile.",
        )

    ordered = sorted(samples, key=lambda sample: sample.adjusted_price_eur)
    total_weight = sum((sample.weight for sample in ordered), Decimal("0"))

    if total_weight <= 0:
        raise DomainError(
            ErrorCode.VALUATION_INSUFFICIENT_COMPARABLES,
            "La somme des poids des comparables doit être strictement positive.",
        )

    target = percentile * total_weight
    cumulative = Decimal("0")
    for sample in ordered:
        cumulative += sample.weight
        if cumulative >= target:
            return sample.adjusted_price_eur

    # Inatteignable en arithmétique exacte ; le dernier prix reste la réponse
    # correcte si un arrondi laissait le cumul juste en deçà de la cible.
    return ordered[-1].adjusted_price_eur


@dataclass(frozen=True, slots=True)
class MarketQuote:
    low_eur: Decimal
    central_eur: Decimal
    high_eur: Decimal
    comparable_count: int
    total_weight: Decimal
    widened_for_small_sample: bool


def market_quote(samples: list[WeightedPrice], ruleset: Ruleset) -> MarketQuote:
    """Cote de marché pondérée.

    L'élargissement pour petit échantillon ne resserre jamais l'intervalle : il
    ne s'applique que si le percentile calculé est plus étroit que la marge
    minimale, ce qu'expriment le `min` et le `max` de la spécification.
    """

    minimum = ruleset.integer(*_GATES, "valuation_min_comparables")
    if len(samples) < minimum:
        raise DomainError(
            ErrorCode.VALUATION_INSUFFICIENT_COMPARABLES,
            f"Au moins {minimum} comparables recevables sont nécessaires.",
            details={"comparable_count": len(samples), "minimum": minimum},
        )

    central = weighted_percentile(samples, Decimal("0.50"))
    low = weighted_percentile(samples, Decimal("0.25"))
    high = weighted_percentile(samples, Decimal("0.75"))

    widened = False
    if len(samples) <= 4:
        interval = ruleset.decimal("valuation_confidence", "small_sample_interval")
        floor = central * (Decimal("1") - interval)
        ceiling = central * (Decimal("1") + interval)
        widened_low = min(low, floor)
        widened_high = max(high, ceiling)
        widened = widened_low != low or widened_high != high
        low, high = widened_low, widened_high

    total_weight = sum((sample.weight for sample in samples), Decimal("0"))

    return MarketQuote(
        low_eur=round_monetary(low),
        central_eur=round_monetary(central),
        high_eur=round_monetary(high),
        comparable_count=len(samples),
        total_weight=total_weight.quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        ),
        widened_for_small_sample=widened,
    )
