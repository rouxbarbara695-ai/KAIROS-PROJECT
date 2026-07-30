from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.shared.rules.ruleset import Ruleset

_SALE_DELAY = ("sale_delay",)


@dataclass(frozen=True, slots=True)
class SaleDelay:
    """Délai de revente attendu, et ce qui l'a produit.

    Le délai nourrit la moitié du pilier liquidité : l'afficher sans ses deux
    entrées reviendrait à demander de croire un nombre.
    """

    days: int
    base_days: int
    multiplier: Decimal
    depth_band: str
    price_band: str
    thin_evidence: bool


def _depth_band(dated_comparables: int) -> str:
    if dated_comparables >= 20:
        return "20_plus"
    if dated_comparables >= 10:
        return "10_19"
    if dated_comparables >= 5:
        return "5_9"
    if dated_comparables >= 3:
        return "3_4"
    return "under_3"


def _price_band(
    price_eur: Decimal, low_eur: Decimal, central_eur: Decimal, high_eur: Decimal
) -> str:
    """Plus on vise haut dans la cote, plus la vente est lente.

    Les bornes sont inclusives vers le bas : vendre *au* prix bas est le cas
    rapide, pas le cas limite.
    """

    if price_eur <= low_eur:
        return "at_or_below_low"
    if price_eur <= central_eur:
        return "at_or_below_central"
    if price_eur <= high_eur:
        return "at_or_below_high"
    return "above_high"


def estimated_sale_delay(
    *,
    dated_comparables: int,
    intended_sale_price_eur: Decimal,
    low_eur: Decimal,
    central_eur: Decimal,
    high_eur: Decimal,
    ruleset: Ruleset,
) -> SaleDelay:
    """Délai attendu : profondeur du marché × ambition du prix, borné.

    Les bornes ne sont pas cosmétiques. Sans plancher, un marché très profond
    produirait un délai de quelques jours qu'aucune vente réelle ne tient ;
    sans plafond, un marché mince produirait un délai si long qu'il cesserait
    d'être une prévision pour devenir un refus déguisé.
    """

    depth_band = _depth_band(dated_comparables)
    price_band = _price_band(intended_sale_price_eur, low_eur, central_eur, high_eur)

    base = int(ruleset.integer(*_SALE_DELAY, "depth_days", depth_band))
    multiplier = ruleset.decimal(*_SALE_DELAY, "price_multipliers", price_band)

    raw = (Decimal(base) * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    minimum = ruleset.integer(*_SALE_DELAY, "minimum_days")
    maximum = ruleset.integer(*_SALE_DELAY, "maximum_days")
    days = int(max(Decimal(minimum), min(Decimal(maximum), raw)))

    return SaleDelay(
        days=days,
        base_days=base,
        multiplier=multiplier,
        depth_band=depth_band,
        price_band=price_band,
        # En deçà du minimum de comparables datés, l'estimation repose sur trop
        # peu d'observations pour être présentée comme une prévision.
        thin_evidence=dated_comparables
        < int(ruleset.integer(*_SALE_DELAY, "minimum_dated_comparables")),
    )
