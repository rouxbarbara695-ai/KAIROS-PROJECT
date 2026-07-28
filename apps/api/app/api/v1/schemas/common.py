from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer


def _reject_json_numbers(value: Any) -> Any:
    """api-contract.md : montants, taux, ROI et scores sont des chaînes
    décimales JSON, jamais des nombres flottants. Un JSON number (int/float)
    arrive ici comme `int`/`float` Python ; on le refuse explicitement.
    `Decimal` lui-même est accepté (construction interne, tests)."""

    if isinstance(value, bool | int | float):
        raise ValueError(
            "Un montant/taux/score doit être une chaîne décimale, pas un nombre JSON."
        )
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Chaîne décimale invalide : {value!r}") from exc
    return value


DecimalString = Annotated[
    Decimal,
    BeforeValidator(_reject_json_numbers),
    PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json"),
]
