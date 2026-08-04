from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.adapters.attempt_log import LoginAttemptLog
from app.identity.application.authentication import log_in, log_out
from app.shared.config import Settings, get_settings
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.principal_provider import SESSION_COOKIE
from app.shared.infrastructure.redis_client import get_redis

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """Pose le cookie de session.

    `HttpOnly` pour qu'aucun script ne puisse le lire, `SameSite=Lax` pour
    qu'aucun site tiers ne puisse déclencher d'action authentifiée, `Secure`
    hors développement local — un cookie de session qui transite en clair est
    un cookie qu'on peut voler sur un réseau public.
    """

    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "local",
        max_age=settings.session_lifetime_days * 24 * 3600,
        path="/",
    )


def _client_ip(request: Request) -> str:
    """L'adresse à laquelle imputer les échecs.

    Derrière un proxy — c'est le cas dès qu'on héberge — `request.client` est
    l'adresse du proxy, la même pour tout le monde : la limitation
    s'appliquerait alors à l'ensemble des visiteurs d'un coup. On lit donc
    l'en-tête transmis par le proxy, en ne gardant que la première adresse,
    celle du client d'origine.

    Lu seul, cet en-tête serait falsifiable : il suffirait d'en inventer un
    nouveau à chaque essai pour repartir d'un compteur vierge. Ce qui l'empêche
    n'est pas ici mais devant — Caddy remplace `X-Forwarded-For` par l'adresse
    réelle du client au lieu d'y ajouter la sienne (voir
    `infra/caddy/Caddyfile`). La garantie appartient donc au relais, et elle
    tombe si l'on place KAIROS derrière un relais qui, lui, se contente
    d'ajouter.

    Même dans ce cas la limitation ne s'effondre pas : le compteur par adresse
    électronique reste insensible à la falsification, et cet en-tête ne donne
    jamais d'accès — il ne fait que répartir un compteur.
    """

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "inconnue"


@router.post("/auth/login")
async def login_route(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> dict[str, str]:
    """Ouvre une session.

    Aucune inscription publique n'existe : KAIROS est mono-organisation et les
    comptes se créent en ligne de commande sur la machine qui héberge la base.
    """

    token = await log_in(
        session,
        email=body.email,
        password=body.password,
        attempts=LoginAttemptLog(redis),
        client_ip=_client_ip(request),
    )
    _set_session_cookie(response, token, settings)
    return {"status": "ok"}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_route(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Révoque la session courante et efface le cookie.

    Les deux, et pas seulement l'un : révoquer sans effacer laisserait le
    navigateur présenter un jeton mort à chaque page, et effacer sans révoquer
    laisserait vivante une session copiée ailleurs.

    Le cookie est effacé même si le jeton était déjà inconnu — se déconnecter
    d'une session qui n'existe plus n'est pas une erreur.
    """

    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await log_out(session, token)
    response.delete_cookie(SESSION_COOKIE, path="/")
