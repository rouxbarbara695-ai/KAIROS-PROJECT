from __future__ import annotations

from decimal import Decimal

import pytest

from app.portfolio.domain.ledger import (
    LedgerKind,
    LedgerMovement,
    cash_balance,
    signed_amount,
)
from app.shared.domain.errors import DomainError


def _movement(kind: LedgerKind, amount: str) -> LedgerMovement:
    return LedgerMovement(kind=kind, amount_eur=Decimal(amount))


def test_every_kind_of_the_schema_has_a_declared_direction() -> None:
    """Une nature ajoutée au schéma sans sens déclaré fausserait la trésorerie
    en silence, donc l'allocation, donc le score."""

    for kind in LedgerKind:
        assert signed_amount(_movement(kind, "100")).copy_abs() == Decimal("100")


def test_contributions_and_receipts_add_while_payments_subtract() -> None:
    assert signed_amount(_movement(LedgerKind.CAPITAL_CONTRIBUTION, "1000")) == Decimal(
        "1000"
    )
    assert signed_amount(_movement(LedgerKind.SALE_RECEIPT, "1700")) == Decimal("1700")
    assert signed_amount(_movement(LedgerKind.PURCHASE_PAYMENT, "950")) == Decimal(
        "-950"
    )
    assert signed_amount(_movement(LedgerKind.WITHDRAWAL, "200")) == Decimal("-200")


def test_the_real_opening_position() -> None:
    """Capital de départ 3 859,20 €, trois montres payées 950, 750 et 1 112 € :
    il doit rester 1 047,20 € de trésorerie."""

    movements = [
        _movement(LedgerKind.CAPITAL_CONTRIBUTION, "3859.20"),
        _movement(LedgerKind.PURCHASE_PAYMENT, "950"),
        _movement(LedgerKind.PURCHASE_PAYMENT, "750"),
        _movement(LedgerKind.PURCHASE_PAYMENT, "1112"),
    ]
    assert cash_balance(movements) == Decimal("1047.20")


def test_adding_capital_mid_course_raises_the_available_cash() -> None:
    """Un apport en cours de route doit débloquer la capacité d'achat sans
    qu'on ait à retoucher l'historique."""

    before = [_movement(LedgerKind.CAPITAL_CONTRIBUTION, "3859.20")]
    after = [*before, _movement(LedgerKind.CAPITAL_CONTRIBUTION, "2000")]
    assert cash_balance(after) - cash_balance(before) == Decimal("2000")


def test_an_empty_ledger_yields_no_cash() -> None:
    assert cash_balance([]) == Decimal("0.00")


def test_an_overdraft_is_reported_not_corrected() -> None:
    """Le registre constate ce qui s'est passé. C'est l'exposition qui refusera
    ensuite de mesurer une allocation sur une trésorerie nulle."""

    movements = [
        _movement(LedgerKind.CAPITAL_CONTRIBUTION, "500"),
        _movement(LedgerKind.PURCHASE_PAYMENT, "800"),
    ]
    assert cash_balance(movements) == Decimal("-300")


def test_the_sign_belongs_to_the_kind_not_to_the_amount() -> None:
    """Autoriser un montant négatif offrirait deux écritures pour un même
    mouvement, et le schéma l'interdit déjà."""

    with pytest.raises(DomainError):
        _movement(LedgerKind.WITHDRAWAL, "-200")
    with pytest.raises(DomainError):
        _movement(LedgerKind.CAPITAL_CONTRIBUTION, "0")
