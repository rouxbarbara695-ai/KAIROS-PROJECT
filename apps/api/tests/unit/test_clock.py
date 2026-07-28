from datetime import UTC, datetime

import pytest

from app.shared.domain.clock import FixedClock, SystemClock


def test_system_clock_returns_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 0


def test_fixed_clock_returns_frozen_value() -> None:
    frozen = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    clock = FixedClock(frozen)
    assert clock.now() == frozen
    assert clock.now() == frozen


def test_fixed_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 7, 28, 12, 0))
