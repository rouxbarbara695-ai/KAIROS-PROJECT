from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.db.models.reference_data import FxRate


@dataclass(frozen=True, slots=True)
class FxResolution:
    rate_to_eur: Decimal
    fx_rate_at: datetime
    fx_source: str
    fx_rate_id: uuid.UUID | None

    def convert(self, amount: Decimal) -> Decimal:
        return (amount * self.rate_to_eur).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


async def resolve_fx(
    session: AsyncSession, currency: str, max_age_hours: int
) -> FxResolution | None:
    """Résout un taux EUR utilisable, ou `None` si aucun taux frais n'existe
    (calculation-spec.md §1 ; jamais de valeur silencieuse — l'appelant doit
    traiter `None` explicitement)."""

    if currency.upper() == "EUR":
        return FxResolution(
            rate_to_eur=Decimal("1"),
            fx_rate_at=datetime.now(UTC),
            fx_source="identity",
            fx_rate_id=None,
        )

    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    row = (
        await session.execute(
            select(FxRate)
            .where(
                FxRate.base_currency == currency.upper(),
                FxRate.quote_currency == "EUR",
                FxRate.observed_at >= cutoff,
            )
            .order_by(FxRate.observed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        return None

    return FxResolution(
        rate_to_eur=Decimal(str(row.rate)),
        fx_rate_at=row.observed_at,
        fx_source=row.source_name,
        fx_rate_id=row.id,
    )
