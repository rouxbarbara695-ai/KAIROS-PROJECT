from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.application.authentication import resolve_session
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.session import get_session

SESSION_COOKIE = "kairos_session"


async def get_current_principal(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """Résout le mandataire depuis le cookie de session.

    Il n'y a plus de mandataire de développement créé à la volée depuis une
    adresse de configuration : c'était commode tant que KAIROS tournait sur un
    poste, et c'était une porte ouverte dès la première mise en ligne. Un
    compte se crée en ligne de commande sur la machine qui héberge la base
    (`python -m app.create_user`).

    Le jeton est lu dans un cookie et non dans un en-tête `Authorization` : un
    cookie `HttpOnly` n'est pas lisible par du JavaScript, donc pas
    exfiltrable par une injection dans l'interface.
    """

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise DomainError(ErrorCode.UNAUTHORIZED, "Authentification requise.")

    return await resolve_session(session, token)
