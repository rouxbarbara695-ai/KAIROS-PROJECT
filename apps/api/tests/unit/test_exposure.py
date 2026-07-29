from __future__ import annotations

from decimal import Decimal

import pytest

from app.portfolio.domain.exposure import PortfolioPosition, exposure_rates
from app.shared.domain.errors import DomainError


def _position(
    cash: str = "1047.20", stock: str = "2812", brand: str = "1862"
) -> PortfolioPosition:
    return PortfolioPosition(
        available_cash_eur=Decimal(cash),
        stock_at_cost_eur=Decimal(stock),
        brand_exposure_at_cost_eur=Decimal(brand),
    )


def test_total_capital_adds_cash_and_stock() -> None:
    assert _position().total_capital_eur == Decimal("3859.20")


def test_real_position_rates(  # noqa: D103
) -> None:
    """Portefeuille réel de référence : 1 047,20 € de trésorerie, trois montres
    achetées 2 812 € dont 1 862 € de Cartier. Un achat Cartier de 500 €."""

    rates = exposure_rates(_position(), Decimal("500"))

    # 500 / 1047.20 — l'allocation se mesure sur la trésorerie mobilisable.
    assert rates.allocation_rate.quantize(Decimal("0.0001")) == Decimal("0.4775")
    # (1862 + 500) / 3859.20 — la concentration se mesure sur le capital total.
    assert rates.brand_concentration_rate.quantize(Decimal("0.0001")) == Decimal(
        "0.6120"
    )
    # 2812 / 3859.20 — au-delà du seuil de 70 % du barème.
    assert rates.capital_immobilization_rate.quantize(Decimal("0.0001")) == Decimal(
        "0.7286"
    )


def test_allocation_uses_cash_while_the_others_use_total_capital() -> None:
    """Les dénominateurs diffèrent volontairement : rapportées à la seule
    trésorerie, immobilisation et concentration dépasseraient 100 % et
    cesseraient d'être des parts."""

    rates = exposure_rates(_position(), Decimal("1047.20"))
    assert rates.allocation_rate == Decimal("1.00000000")
    assert rates.capital_immobilization_rate < Decimal("1")


def test_purchase_is_not_counted_twice() -> None:
    """L'achat envisagé entre dans l'allocation et dans la concentration, mais
    pas dans l'immobilisation : il n'est pas encore en stock."""

    without = exposure_rates(_position(), Decimal("0"))
    with_purchase = exposure_rates(_position(), Decimal("500"))
    assert (
        without.capital_immobilization_rate == with_purchase.capital_immobilization_rate
    )
    assert with_purchase.brand_concentration_rate > without.brand_concentration_rate


def test_a_purchase_of_zero_yields_no_allocation() -> None:
    assert exposure_rates(_position(), Decimal("0")).allocation_rate == Decimal("0E-8")


def test_negative_amounts_are_rejected() -> None:
    with pytest.raises(DomainError):
        _position(cash="-1")
    with pytest.raises(DomainError):
        exposure_rates(_position(), Decimal("-1"))


def test_brand_exposure_cannot_exceed_the_stock() -> None:
    with pytest.raises(DomainError):
        _position(stock="1000", brand="2000")


def test_a_portfolio_without_cash_cannot_be_measured() -> None:
    """Sans trésorerie, l'allocation n'a pas de sens : mieux vaut refuser que
    produire un taux infini ou nul par convention."""

    with pytest.raises(DomainError):
        exposure_rates(_position(cash="0"), Decimal("100"))
