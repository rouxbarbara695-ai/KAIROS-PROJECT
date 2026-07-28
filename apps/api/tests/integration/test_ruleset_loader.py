from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.infrastructure.ruleset_loader import load_ruleset

pytestmark = pytest.mark.integration


def _walk(value: object) -> list[object]:
    if isinstance(value, dict):
        return [leaf for item in value.values() for leaf in _walk(item)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in _walk(item)]
    return [value]


async def test_seeded_ruleset_loads_without_any_float(
    db_session: AsyncSession,
) -> None:
    """Un décodage JSON standard produirait des flottants pour tous les taux
    du ruleset, ce qu'interdit la règle 2. Le barème complet est parcouru."""

    ruleset = await load_ruleset(db_session, "1.0.0")

    leaves = _walk(ruleset.config)
    assert leaves, "le ruleset seedé ne doit pas être vide"
    assert not [leaf for leaf in leaves if isinstance(leaf, float)]


async def test_seeded_constants_match_the_specification(
    db_session: AsyncSession,
) -> None:
    ruleset = await load_ruleset(db_session, "1.0.0")

    assert ruleset.decimal("comparable", "set_premium", "full_set") == Decimal("0.20")
    assert ruleset.decimal("comparable", "source_reliability", "a") == Decimal("1.00")
    assert ruleset.decimal("comparable", "outlier", "mad_scale") == Decimal("1.4826")
    assert ruleset.integer("comparable", "outlier", "minimum_count") == 4


async def test_missing_ruleset_version_is_reported(db_session: AsyncSession) -> None:
    with pytest.raises(DomainError) as exc:
        await load_ruleset(db_session, "9.9.9")
    assert exc.value.code is ErrorCode.RULESET_MISSING


async def test_missing_constant_names_its_path(db_session: AsyncSession) -> None:
    ruleset = await load_ruleset(db_session, "1.0.0")
    with pytest.raises(DomainError) as exc:
        ruleset.decimal("comparable", "set_premium", "inexistant")
    assert exc.value.code is ErrorCode.RULESET_MISSING
    assert "set_premium" in exc.value.message
