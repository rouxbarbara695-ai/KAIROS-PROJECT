from __future__ import annotations

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config import Settings, get_settings
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.accounts import (
    Portfolio,
    PortfolioMember,
    User,
)
from app.shared.infrastructure.db.session import get_session

_DEFAULT_PORTFOLIO_NAME = "Portefeuille par défaut"


async def get_current_principal(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Résout l'utilisateur de développement unique (Q-01) et garantit
    l'existence d'un portefeuille par défaut dont il est membre. Un
    adaptateur d'authentification réel remplacera cette fonction sans
    changer la forme de `Principal` consommée par les routes."""

    email = settings.dev_principal_email
    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None:
        user = User(email=email)
        session.add(user)
        await session.flush()

    membership_rows = (
        (
            await session.execute(
                select(PortfolioMember.portfolio_id).where(
                    PortfolioMember.user_id == user.id
                )
            )
        )
        .scalars()
        .all()
    )

    if not membership_rows:
        portfolio = Portfolio(name=_DEFAULT_PORTFOLIO_NAME)
        session.add(portfolio)
        await session.flush()
        session.add(
            PortfolioMember(portfolio_id=portfolio.id, user_id=user.id, role="owner")
        )
        await session.flush()
        membership_rows = [portfolio.id]

    await session.commit()

    return Principal(user_id=user.id, portfolio_ids=frozenset(membership_rows))
