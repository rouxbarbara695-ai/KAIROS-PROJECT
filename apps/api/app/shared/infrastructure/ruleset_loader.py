from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.rules.ruleset import Ruleset


async def load_ruleset(session: AsyncSession, version: str) -> Ruleset:
    """Charge un ruleset immuable par sa version.

    Le JSON est relu depuis son texte source avec `parse_float=Decimal` : un
    décodage standard produirait des flottants pour les taux et les barèmes,
    ce qu'interdit la règle 2. Passer par le texte préserve exactement les
    décimales telles qu'écrites dans le ruleset.
    """

    row = (
        await session.execute(
            text("select cast(config as text) from rulesets where version = :version"),
            {"version": version},
        )
    ).scalar_one_or_none()

    if row is None:
        raise DomainError(
            ErrorCode.RULESET_MISSING,
            f"Ruleset {version} introuvable.",
            details={"ruleset_version": version},
        )

    config: dict[str, Any] = json.loads(row, parse_float=Decimal)
    return Ruleset(version=version, config=config, raw_config=row)
