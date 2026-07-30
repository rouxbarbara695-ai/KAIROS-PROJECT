from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.db.models.strategies import Strategy, StrategyVersion

DEFAULT_STRATEGY_NAME = "Stratégie par défaut"

# Clé de `strategy_versions.settings`. La plateforme de revente est une
# décision de stratégie, pas une propriété de l'annonce achetée : on choisit
# où revendre, on ne le subit pas de l'endroit où l'on a acheté.
RESALE_PLATFORM = "resale_platform_code"


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


async def record_strategy_version(
    session: AsyncSession,
    portfolio_id: uuid.UUID,
    ruleset_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    *,
    minimum_roi: Decimal | None = None,
    minimum_profit_eur: Decimal | None = None,
    maximum_allocation_rate: Decimal | None = None,
    negotiation_buffer: Decimal | None = None,
    resale_platform_code: str | None = None,
    clear_resale_platform: bool = False,
) -> StrategyVersion:
    """Ouvre une nouvelle version de la stratégie par défaut.

    Une version n'est jamais modifiée : `strategy_versions` est append-only, et
    à raison — une analyse figée référence la version qui l'a produite, et la
    réécrire rendrait ce verdict inexplicable après coup.

    Les champs absents sont repris de la version courante. Une stratégie se
    corrige d'un paramètre à la fois ; exiger la saisie complète à chaque
    ajustement inviterait à la faute de recopie.
    """

    current = await active_strategy_version(
        session, portfolio_id, ruleset_id, actor_user_id
    )

    settings = dict(current.settings)
    if clear_resale_platform:
        settings.pop(RESALE_PLATFORM, None)
    elif resale_platform_code is not None:
        settings[RESALE_PLATFORM] = resale_platform_code

    version = StrategyVersion(
        portfolio_id=portfolio_id,
        strategy_id=current.strategy_id,
        version=current.version + 1,
        ruleset_id=ruleset_id,
        valid_from=datetime.now(UTC),
        minimum_roi=(current.minimum_roi if minimum_roi is None else minimum_roi),
        minimum_profit_eur=(
            current.minimum_profit_eur
            if minimum_profit_eur is None
            else minimum_profit_eur
        ),
        maximum_allocation_rate=(
            current.maximum_allocation_rate
            if maximum_allocation_rate is None
            else maximum_allocation_rate
        ),
        negotiation_buffer=(
            current.negotiation_buffer
            if negotiation_buffer is None
            else negotiation_buffer
        ),
        settings=settings,
        created_by_user_id=actor_user_id,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version
