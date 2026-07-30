from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.rules.ruleset import Ruleset

_SUBSCORE = Decimal("0.0001")


def interpolate(points: list[tuple[Decimal, Decimal]], value: Decimal) -> Decimal:
    """Interpolation linéaire sur une courbe du ruleset, bornée 0–100.

    Les courbes sont données comme des paires (entrée, score). Elles peuvent
    être croissantes — le profit — ou décroissantes — le délai : l'orientation
    est portée par la donnée, pas par le code, sans quoi ajouter une courbe
    obligerait à modifier le moteur.
    """

    if not points:
        raise DomainError(
            ErrorCode.RULESET_MISSING, "Courbe de score vide dans le ruleset."
        )

    ordered = sorted(points, key=lambda point: point[0])

    if value <= ordered[0][0]:
        return _clamp(ordered[0][1])
    if value >= ordered[-1][0]:
        return _clamp(ordered[-1][1])

    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:], strict=False):
        if x0 <= value <= x1:
            if x1 == x0:
                return _clamp(y1)
            ratio = (value - x0) / (x1 - x0)
            return _clamp(y0 + ratio * (y1 - y0))

    return _clamp(ordered[-1][1])


def _clamp(value: Decimal) -> Decimal:
    bounded = min(max(value, Decimal("0")), Decimal("100"))
    return bounded.quantize(_SUBSCORE, rounding=ROUND_HALF_UP)


def curve(ruleset: Ruleset, name: str) -> list[tuple[Decimal, Decimal]]:
    raw = ruleset.value("scoring", "curves", name)
    if not isinstance(raw, list):
        raise DomainError(
            ErrorCode.RULESET_MISSING,
            f"Courbe « {name} » absente ou malformée dans le ruleset "
            f"{ruleset.version}.",
            details={"curve": name},
        )

    points: list[tuple[Decimal, Decimal]] = []
    for entry in raw:
        if not isinstance(entry, list) or len(entry) != 2:
            raise DomainError(
                ErrorCode.RULESET_MISSING,
                f"Point invalide dans la courbe « {name} ».",
                details={"curve": name},
            )
        points.append((Decimal(str(entry[0])), Decimal(str(entry[1]))))
    return points
