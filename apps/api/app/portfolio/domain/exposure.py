from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.shared.domain.errors import DomainError, ErrorCode

_RATE = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class PortfolioPosition:
    """Situation du portefeuille au moment d'une analyse.

    Le stock est valorisé **au coût d'acquisition**, jamais à l'estimation.
    Sinon relever ses propres estimations améliorerait mécaniquement le score
    de portefeuille : l'outil se noterait lui-même. La plus-value latente reste
    affichable, mais elle n'entre dans aucun calcul.
    """

    available_cash_eur: Decimal
    stock_at_cost_eur: Decimal
    brand_exposure_at_cost_eur: Decimal

    def __post_init__(self) -> None:
        for label, value in (
            ("available_cash_eur", self.available_cash_eur),
            ("stock_at_cost_eur", self.stock_at_cost_eur),
            ("brand_exposure_at_cost_eur", self.brand_exposure_at_cost_eur),
        ):
            if value < 0:
                raise DomainError(
                    ErrorCode.VALIDATION_ERROR,
                    f"« {label} » ne peut pas être négatif.",
                    field=label,
                )
        if self.brand_exposure_at_cost_eur > self.stock_at_cost_eur:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                "L'exposition sur une marque ne peut pas dépasser le stock total.",
                field="brand_exposure_at_cost_eur",
            )

    @property
    def total_capital_eur(self) -> Decimal:
        return self.available_cash_eur + self.stock_at_cost_eur


@dataclass(frozen=True, slots=True)
class ExposureRates:
    allocation_rate: Decimal
    brand_concentration_rate: Decimal
    capital_immobilization_rate: Decimal


def _rate(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Un portefeuille sans capital ne permet aucun calcul d'exposition.",
            field="available_cash_eur",
        )
    return (numerator / denominator).quantize(_RATE, rounding=ROUND_HALF_UP)


def exposure_rates(
    position: PortfolioPosition, planned_purchase_cost_eur: Decimal
) -> ExposureRates:
    """Les trois taux du pilier portefeuille.

    Les dénominateurs diffèrent volontairement. L'allocation mesure une
    capacité de paiement : elle se rapporte à la trésorerie disponible, seule
    ressource réellement mobilisable — c'est d'ailleurs ce que le barème
    nomme « impact cash ». L'immobilisation et la concentration décrivent la
    composition du patrimoine : rapportées à la seule trésorerie, elles
    dépasseraient couramment 100 % et cesseraient d'être des parts.
    """

    if planned_purchase_cost_eur < 0:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Le coût d'achat envisagé ne peut pas être négatif.",
            field="planned_purchase_cost_eur",
        )

    total = position.total_capital_eur

    return ExposureRates(
        allocation_rate=_rate(planned_purchase_cost_eur, position.available_cash_eur),
        brand_concentration_rate=_rate(
            position.brand_exposure_at_cost_eur + planned_purchase_cost_eur, total
        ),
        # Le capital immobilisé est le stock lui-même : ce qui est en montre
        # n'est pas disponible. L'achat envisagé n'y figure pas encore — il est
        # déjà compté dans l'allocation.
        capital_immobilization_rate=_rate(position.stock_at_cost_eur, total),
    )
