"""Retrouve le portefeuille d'une opportunité, avant toute opération.

Les clés d'idempotence sont portées par `(portfolio_id, idempotency_key)` : la
place doit donc être réservée avant que l'opération ne s'exécute, alors que le
portefeuille n'est connu qu'en lisant l'opportunité.

Cette lecture double celle que fait ensuite le cas d'usage. C'est assumé : une
requête sur clé primaire coûte moins qu'un double achat, et la duplication a
un effet secondaire utile — une opportunité inconnue est refusée avant même
qu'une clé soit consommée.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.opportunities import Opportunity


async def portfolio_of_opportunity(
    session: AsyncSession, principal: Principal, opportunity_id: uuid.UUID
) -> uuid.UUID:
    portfolio_id = (
        await session.execute(
            select(Opportunity.portfolio_id).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()

    # 404 et non 403, comme partout ailleurs : l'existence d'une opportunité
    # étrangère ne doit pas se déduire de la différence de code.
    if portfolio_id is None or not principal.owns_portfolio(portfolio_id):
        raise DomainError(ErrorCode.NOT_FOUND, "Opportunité introuvable.")

    return portfolio_id
