from decimal import Decimal

import pytest

from app.shared.domain.money import Money


def test_money_accepts_string_and_decimal() -> None:
    assert Money("1800.00", "eur").rounded() == Decimal("1800.00")
    assert Money(Decimal("1800"), "EUR").rounded() == Decimal("1800.00")


def test_money_rejects_float_construction() -> None:
    with pytest.raises(TypeError):
        Money(1800.0, "EUR")


def test_money_uppercases_currency() -> None:
    assert Money("10", "eur").currency == "EUR"


def test_money_rejects_invalid_currency_code() -> None:
    with pytest.raises(ValueError):
        Money("10", "EU")


def test_money_arithmetic_same_currency() -> None:
    total = Money("100", "EUR") + Money("50.5", "EUR")
    assert total.rounded() == Decimal("150.50")


def test_money_arithmetic_rejects_mixed_currency() -> None:
    with pytest.raises(ValueError):
        Money("100", "EUR") + Money("100", "USD")


def test_money_rounding_half_up() -> None:
    assert Money("1.005", "EUR").rounded() == Decimal("1.01")
    assert Money("1.004", "EUR").rounded() == Decimal("1.00")
