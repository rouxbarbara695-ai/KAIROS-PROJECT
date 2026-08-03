from __future__ import annotations

import pytest

from app.operations.domain.workflow import allowed_transitions, ensure_transition
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.infrastructure.db.models.enums import OpportunityStatus as Status


def test_every_status_declares_its_transitions() -> None:
    """Un statut oublié lèverait un `KeyError` au premier passage, c'est-à-dire
    en production plutôt qu'ici."""

    for status in Status:
        assert isinstance(allowed_transitions(status), frozenset)


def test_the_nominal_cycle_is_traversable() -> None:
    chain = [
        Status.WATCHING,
        Status.BUY,
        Status.PURCHASED,
        Status.IN_STOCK,
        Status.LISTED_FOR_SALE,
        Status.AWAITING_BUYER_PAYMENT,
        Status.AWAITING_PAYOUT,
        Status.SOLD,
    ]
    for current, following in zip(chain, chain[1:], strict=False):
        ensure_transition(current, following)


def test_a_sale_is_terminal() -> None:
    """Une vente ne se défait pas : on la corrige par une écriture inverse, pas
    en revenant en arrière."""

    assert allowed_transitions(Status.SOLD) == frozenset()
    with pytest.raises(DomainError) as raised:
        ensure_transition(Status.SOLD, Status.IN_STOCK)
    assert raised.value.code is ErrorCode.INVALID_TRANSITION


def test_buying_without_the_intention_is_refused() -> None:
    """`watching` ne mène pas directement à `purchased` : la spécification
    passe par une intention d'achat, et l'inventer ici serait inventer une
    règle métier."""

    with pytest.raises(DomainError):
        ensure_transition(Status.WATCHING, Status.PURCHASED)


def test_the_refusal_says_what_is_possible() -> None:
    """Un refus qui n'énonce pas les issues force l'utilisateur à deviner."""

    with pytest.raises(DomainError) as raised:
        ensure_transition(Status.IN_STOCK, Status.SOLD)
    assert raised.value.details["allowed"] == ["listed_for_sale"]


def test_staying_put_is_not_a_transition() -> None:
    with pytest.raises(DomainError) as raised:
        ensure_transition(Status.IN_STOCK, Status.IN_STOCK)
    assert raised.value.code is ErrorCode.INVALID_TRANSITION


def test_an_abandoned_opportunity_can_be_reopened() -> None:
    """Une réouverture conserve tout l'historique : c'est une transition de
    plus, pas un effacement."""

    ensure_transition(Status.ABANDONED, Status.WATCHING)
