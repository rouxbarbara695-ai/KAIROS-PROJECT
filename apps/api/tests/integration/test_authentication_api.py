from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.application.authentication import create_user, log_in
from app.identity.domain.credentials import fingerprint
from app.shared.domain.errors import DomainError
from app.shared.infrastructure.principal_provider import SESSION_COOKIE
from tests.conftest import TEST_EMAIL, TEST_PASSWORD

pytestmark = pytest.mark.integration


async def test_an_anonymous_request_is_refused(anonymous_client: AsyncClient) -> None:
    """Le défaut corrigé : l'utilisateur était créé à la volée depuis une
    adresse en configuration, donc exposé sur Internet, KAIROS donnait le
    portefeuille à quiconque connaissait l'URL."""

    response = await anonymous_client.get("/api/v1/opportunities")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_logging_in_opens_a_session(anonymous_client: AsyncClient) -> None:
    response = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    assert SESSION_COOKIE in response.cookies

    authenticated = await anonymous_client.get("/api/v1/me")
    assert authenticated.status_code == 200


async def test_the_session_cookie_is_not_readable_by_scripts(
    anonymous_client: AsyncClient,
) -> None:
    """`HttpOnly` : une injection dans l'interface ne doit pas pouvoir
    exfiltrer la session. `SameSite` : un site tiers ne doit pas pouvoir
    déclencher d'action authentifiée."""

    response = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header


async def test_a_wrong_password_is_refused(anonymous_client: AsyncClient) -> None:
    response = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": "ce-n-est-pas-le-bon-mot-de-passe"},
    )
    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies


async def test_an_unknown_address_says_exactly_what_a_wrong_password_says(
    anonymous_client: AsyncClient,
) -> None:
    """Distinguer les deux dirait à un inconnu quelles adresses ont un
    compte."""

    unknown = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"email": "personne@nulle-part.test", "password": TEST_PASSWORD},
    )
    wrong = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": "mauvais-mot-de-passe-long"},
    )

    assert unknown.status_code == wrong.status_code == 401
    # L'enveloppe porte un identifiant de requête, propre à chaque appel : ce
    # qui doit être identique, c'est ce que l'erreur dit.
    assert unknown.json()["error"]["code"] == wrong.json()["error"]["code"]
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


async def test_the_clear_token_is_never_stored(
    db_session: AsyncSession, anonymous_client: AsyncClient
) -> None:
    """Une base lue par un tiers ne doit lui donner aucune session
    utilisable."""

    response = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    token = response.cookies[SESSION_COOKIE]

    stored = set(
        (
            await db_session.execute(
                text("select token_fingerprint from user_sessions")
            )
        ).scalars()
    )
    assert token not in stored
    assert stored


async def test_logging_out_revokes_the_session(
    anonymous_client: AsyncClient,
) -> None:
    await anonymous_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert (await anonymous_client.get("/api/v1/me")).status_code == 200

    assert (await anonymous_client.post("/api/v1/auth/logout")).status_code == 204
    assert (await anonymous_client.get("/api/v1/me")).status_code == 401


async def test_a_revoked_token_stays_refused(
    db_session: AsyncSession, anonymous_client: AsyncClient
) -> None:
    """Le cookie effacé ne suffirait pas : un jeton copié ailleurs doit cesser
    de fonctionner, ce qu'un jeton auto-porteur ne permettrait pas."""

    response = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    token = response.cookies[SESSION_COOKIE]
    await anonymous_client.post("/api/v1/auth/logout")

    anonymous_client.cookies.set(SESSION_COOKIE, token)
    assert (await anonymous_client.get("/api/v1/me")).status_code == 401


async def test_an_expired_session_is_refused(
    db_session: AsyncSession, anonymous_client: AsyncClient
) -> None:
    token = await log_in(db_session, email=TEST_EMAIL, password=TEST_PASSWORD)

    # La contrainte `expires_at > issued_at` interdit d'antidater la seule
    # expiration — et elle a raison : une session qui expire avant d'être
    # émise n'existe pas. On recule donc les deux dates ensemble, comme une
    # session réellement ouverte il y a longtemps.
    now = datetime.now(UTC)
    await db_session.execute(
        text(
            "update user_sessions set issued_at = :opened, expires_at = :closed, "
            "last_seen_at = :opened where token_fingerprint = :fingerprint"
        ),
        {
            "opened": now - timedelta(days=60),
            "closed": now - timedelta(days=30),
            "fingerprint": fingerprint(token),
        },
    )
    await db_session.commit()

    anonymous_client.cookies.set(SESSION_COOKIE, token)
    assert (await anonymous_client.get("/api/v1/me")).status_code == 401


async def test_a_forged_token_is_refused(anonymous_client: AsyncClient) -> None:
    anonymous_client.cookies.set(SESSION_COOKIE, "jeton-invente-de-toutes-pieces")
    assert (await anonymous_client.get("/api/v1/me")).status_code == 401


async def test_no_public_registration_exists(anonymous_client: AsyncClient) -> None:
    """KAIROS est mono-organisation : un formulaire d'inscription ouvert sur un
    portefeuille personnel serait une porte, pas une fonctionnalité."""

    for path in ("/api/v1/auth/register", "/api/v1/users", "/api/v1/auth/signup"):
        assert (await anonymous_client.post(path, json={})).status_code == 404


async def test_a_short_password_is_refused(db_session: AsyncSession) -> None:
    """Un secret trop court se casse hors ligne quelle que soit la qualité du
    hachage."""

    with pytest.raises(DomainError):
        await create_user(db_session, email="court@kairos.local", password="court")


async def test_changing_the_password_closes_open_sessions(
    db_session: AsyncSession, anonymous_client: AsyncClient
) -> None:
    """Sinon un appareil perdu garderait son accès malgré le changement.

    Sur un compte dédié : révoquer les sessions du compte partagé par la suite
    couperait tous les tests suivants, qui s'appuient sur une session ouverte
    une fois pour toutes.
    """

    from app.identity.application.authentication import revoke_all

    email = "rotation@kairos.local"
    user = await create_user(
        db_session, email=email, password="premier-mot-de-passe-long"
    )
    token = await log_in(db_session, email=email, password="premier-mot-de-passe-long")

    anonymous_client.cookies.set(SESSION_COOKIE, token)
    assert (await anonymous_client.get("/api/v1/me")).status_code == 200

    await create_user(db_session, email=email, password="second-mot-de-passe-long")
    await revoke_all(db_session, user.id)

    assert (await anonymous_client.get("/api/v1/me")).status_code == 401
