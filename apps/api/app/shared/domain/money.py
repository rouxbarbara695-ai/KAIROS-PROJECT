from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, getcontext

# CLAUDE.md règle 2 : Decimal partout, jamais de flottant, pour montants,
# taux et scores. Précision interne >= 8 décimales (calculation-spec.md).
getcontext().prec = 28

_CENTS = Decimal("0.01")


def to_decimal(value: Decimal | int | str) -> Decimal:
    """Convertit une valeur explicite en Decimal. Refuse `float` : un flottant
    binaire ne représente pas exactement les montants décimaux et sa
    conversion silencieuse masquerait des erreurs d'arrondi."""
    if isinstance(value, float):
        raise TypeError(
            "Un montant ne peut pas être construit depuis un float ; "
            "utiliser une chaîne ou un Decimal (CLAUDE.md règle 2)."
        )
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


@dataclass(frozen=True, slots=True)
class Money:
    """Montant immuable dans une devise. La précision interne est conservée
    jusqu'à la sortie ; l'arrondi ROUND_HALF_UP à 2 décimales n'a lieu qu'à
    l'affichage/la persistance via `.rounded()`."""

    amount: Decimal
    currency: str

    def __init__(self, amount: Decimal | int | str, currency: str) -> None:
        object.__setattr__(self, "amount", to_decimal(amount))
        object.__setattr__(self, "currency", currency.upper())
        if len(self.currency) != 3:
            raise ValueError(f"Code devise invalide : {currency!r}")

    def rounded(self) -> Decimal:
        return self.amount.quantize(_CENTS, rounding=ROUND_HALF_UP)

    def _require_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Devises incompatibles : {self.currency} vs {other.currency}"
            )

    def __add__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int | str) -> Money:
        return Money(self.amount * to_decimal(factor), self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __str__(self) -> str:
        return f"{self.rounded()} {self.currency}"
