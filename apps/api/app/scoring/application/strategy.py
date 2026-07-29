from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.db.models.strategies import Strategy, StrategyVersion

DEFAULT_STRATEGY_NAME = "Stratégie par défaut"


async def active_strategy_version(
    session: AsyncSession,
    portfolio_id: uuid.UUID,
    ruleset_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> StrategyVersion:
    """Version de stratégie en vigueur, créée à la première analyse si besoin.

    Les seuils par défaut — ROI minimal, profit minimal, allocation maximale,
    tampon de négociation — ne sont pas inventés ici : ce sont ceux du schéma,
    qui fait foi. Les laisser porter par une version en base plutôt que par du
    code garantit qu'une analyse reste rejouable même après un changement de
    stratégie, puisqu'elle référence la version qui l'a produite.
    """

    existing = (
        await session.execute(
            select(StrategyVersion)
            .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
            .where(
                StrategyVersion.portfolio_id == portfolio_id,
                Strategy.name == DEFAULT_STRATEGY_NAME,
            )
            .order_by(StrategyVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    strategy = (
        await session.execute(
            select(Strategy).where(
                Strategy.portfolio_id == portfolio_id,
                Strategy.name == DEFAULT_STRATEGY_NAME,
            )
        )
    ).scalar_one_or_none()

    if strategy is None:
        strategy = Strategy(
            portfolio_id=portfolio_id,
            name=DEFAULT_STRATEGY_NAME,
            created_by_user_id=actor_user_id,
        )
        session.add(strategy)
        await session.flush()

    version = StrategyVersion(
        portfolio_id=portfolio_id,
        strategy_id=strategy.id,
        version=1,
        ruleset_id=ruleset_id,
        valid_from=datetime.now(UTC),
        created_by_user_id=actor_user_id,
    )
    session.add(version)
    await session.flush()
    return version
