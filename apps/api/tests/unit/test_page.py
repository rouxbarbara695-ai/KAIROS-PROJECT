from datetime import UTC, datetime

import pytest

from app.shared.domain.errors import DomainError
from app.shared.domain.page import (
    CursorPosition,
    clamp_limit,
    decode_cursor,
    encode_cursor,
)


def test_cursor_roundtrip() -> None:
    position = CursorPosition(
        created_at=datetime(2026, 7, 28, 12, 0, tzinfo=UTC), id="abc-123"
    )
    decoded = decode_cursor(encode_cursor(position))
    assert decoded == position


def test_decode_invalid_cursor_raises_domain_error() -> None:
    with pytest.raises(DomainError):
        decode_cursor("not-a-valid-cursor!!")


def test_clamp_limit_defaults() -> None:
    assert clamp_limit(None) == 20


def test_clamp_limit_caps_at_max() -> None:
    assert clamp_limit(1000) == 100


def test_clamp_limit_rejects_zero_or_negative() -> None:
    with pytest.raises(DomainError):
        clamp_limit(0)
