from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.application.authentication import log_in, log_out
from app.shared.config import Settings, get_settings
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.principal_provider import SESSION_COOKIE

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


@router.post("/auth/login")
async def login_route(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Ouvre une session.

    Aucune inscription publique n'existe : KAIROS est mono-organisation et les
    comptes se créent en ligne de commande sur la machine qui héberge la base.
    """

    token = await log_in(session, email=body.email, password=body.password)
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
