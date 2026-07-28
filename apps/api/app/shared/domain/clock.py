from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """Horloge réelle, toujours UTC (CLAUDE.md : tous les timestamps en UTC)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Horloge gelée pour les tests."""

    def __init__(self, fixed: datetime) -> None:
        if fixed.tzinfo is None:
            raise ValueError("FixedClock exige un datetime avec fuseau (UTC).")
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed
