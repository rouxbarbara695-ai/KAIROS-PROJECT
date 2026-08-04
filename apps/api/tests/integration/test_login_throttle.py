from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.identity.domain.throttle import (
    MAX_FAILURES_PER_IP,
    WINDOW_SECONDS,
)
from app.shared.infrastructure.principal_provider import SESSION_COOKIE
from tests.conftest import TEST_EMAIL, TEST_PASSWORD
from tests.fake_redis import FakeRedis

pytestmark = pytest.mark.integration

_WRONG = "ce-n-est-pas-le-bon-mot-de-passe"


async def _attempt(client: AsyncClient, password: str, *, ip: str | None = None) -> int:
    headers = {"x-forwarded-for": ip} if ip else {}
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": password},
        headers=headers,
    )
    return response.status_code


async def test_a_burst_of_wrong_passwords_is_eventually_refused(
    anonymous_client: AsyncClient,
) -> None:
    """Le défaut corrigé : la route de connexion est publique, et chaque essai
    déclenche un calcul Argon2 volontairement lent. Sans limitation, une rafale
    sature l'API sans même avoir à trouver le mot de passe."""

    for _ in range(MAX_FAILURES_PER_IP):
        assert await _attempt(anonymous_client, _WRONG) == 401

    response = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": _WRONG},
    )
    assert response.status_code == 429
    error = response.json()["error"]
    assert error["code"] == "RATE_LIMITED"
    assert error["details"]["retry_after_seconds"] == WINDOW_SECONDS


async def test_the_limit_holds_even_against_the_right_password(
    anonymous_client: AsyncClient,
) -> None:
    """La contrepartie assumée : une fois la limite atteinte, le bon mot de
    passe est refusé lui aussi.

    Il ne peut pas en aller autrement. Laisser passer la bonne réponse
    reviendrait à répondre « ce mot de passe était le bon » — soit exactement
    l'information que l'attaquant cherche, offerte au moment où on prétend le
    bloquer.
    """

    for _ in range(MAX_FAILURES_PER_IP):
        await _attempt(anonymous_client, _WRONG)

    assert await _attempt(anonymous_client, TEST_PASSWORD) == 429


async def test_a_successful_login_clears_the_counters(
    anonymous_client: AsyncClient, fake_redis: FakeRedis
) -> None:
    """Sans cela, trois fautes de frappe suivies d'une connexion réussie
    laisseraient un budget entamé pour les cinq minutes suivantes."""

    for _ in range(3):
        await _attempt(anonymous_client, _WRONG)
    assert fake_redis.values

    assert await _attempt(anonymous_client, TEST_PASSWORD) == 200
    assert fake_redis.values == {}


async def test_a_successful_login_never_consumes_the_budget(
    anonymous_client: AsyncClient, fake_redis: FakeRedis
) -> None:
    """Seuls les échecs comptent. Compter les tentatives punirait l'usage
    normal : se connecter souvent n'est pas suspect."""

    assert await _attempt(anonymous_client, TEST_PASSWORD) == 200
    assert fake_redis.values == {}


async def test_the_counters_are_bounded_in_time(
    anonymous_client: AsyncClient, fake_redis: FakeRedis
) -> None:
    """Sans expiration, le blocage serait définitif : un compteur qui ne
    retombe jamais transforme un ralentissement en verrou."""

    await _attempt(anonymous_client, _WRONG)
    assert set(fake_redis.expirations.values()) == {WINDOW_SECONDS}


async def test_failures_are_counted_per_origin(
    anonymous_client: AsyncClient,
) -> None:
    """Une adresse IP bloquée ne bloque pas les autres.

    C'est la raison d'être du compteur par IP : derrière un hébergeur, toutes
    les requêtes arrivent par le même proxy, et un compteur global
    verrouillerait tout le monde dès qu'un seul attaquant s'agite.
    """

    for _ in range(MAX_FAILURES_PER_IP):
        await _attempt(anonymous_client, _WRONG, ip="203.0.113.7")
    assert await _attempt(anonymous_client, _WRONG, ip="203.0.113.7") == 429

    assert await _attempt(anonymous_client, TEST_PASSWORD, ip="198.51.100.4") == 200


async def test_a_forwarded_chain_is_read_from_its_first_address(
    anonymous_client: AsyncClient, fake_redis: FakeRedis
) -> None:
    """`X-Forwarded-For` s'allonge à chaque relais : le client d'origine est en
    tête, les proxies suivent. Compter sur le dernier reviendrait à imputer les
    échecs au proxy, donc à tout le monde."""

    await _attempt(anonymous_client, _WRONG, ip="203.0.113.7, 10.0.0.1, 10.0.0.2")
    assert any("203.0.113.7" in key for key in fake_redis.values)


async def test_login_still_works_when_the_counter_is_unreachable(
    anonymous_client: AsyncClient, fake_redis: FakeRedis
) -> None:
    """Le compteur est un filet, pas la frontière de sécurité — celle-ci reste
    le mot de passe. Refuser toute connexion parce que Redis est tombé
    enfermerait le propriétaire dehors pour une panne d'infrastructure."""

    fake_redis.broken = True

    response = await anonymous_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    assert SESSION_COOKIE in response.cookies


async def test_a_wrong_password_is_still_refused_when_the_counter_is_unreachable(
    anonymous_client: AsyncClient, fake_redis: FakeRedis
) -> None:
    """La panne du compteur ne doit rien relâcher d'autre : elle ouvre la
    limitation, jamais l'authentification."""

    fake_redis.broken = True

    assert await _attempt(anonymous_client, _WRONG) == 401
