"""Ce que `ETag` et `If-Match` empêchent : l'écrasement silencieux.

Le scénario n'a rien d'exotique. Deux onglets ouvrent la même fiche. L'un
corrige l'état de la montre, l'autre le vendeur. Le second enregistre en
dernier, sur une lecture périmée, et la correction du premier disparaît sans
que personne ne l'apprenne.

Les tests partent donc de deux lectures de la même version, comme les deux
onglets.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def _opportunity(client: AsyncClient, portfolio_id: uuid.UUID) -> dict:
    response = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(portfolio_id),
            "source": {"mode": "manual", "manual_identifier": "CONC-001"},
            "watch": {"brand": "Longines", "reference": "L2.257.4.57.6"},
            "seller": {"country_code": "FR", "seller_type": "private"},
            "price": {"amount": "1800.00", "currency": "EUR"},
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _if_match(payload: dict) -> dict[str, str]:
    return {"If-Match": f'"version-{payload["version"]}"'}


async def test_every_reading_carries_its_version(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Sans `ETag` sur la lecture, le client n'a rien à citer dans `If-Match`."""

    created = await _opportunity(client, default_portfolio_id)

    read = await client.get(f"/api/v1/opportunities/{created['id']}")
    assert read.status_code == 200, read.text
    assert read.headers["ETag"] == f'"version-{read.json()["version"]}"'


async def test_a_correction_moves_the_version(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    created = await _opportunity(client, default_portfolio_id)

    corrected = await client.patch(
        f"/api/v1/opportunities/{created['id']}/watch-profile",
        json={"cosmetic_condition": "good", "reason": "Rayures constatées"},
        headers=_if_match(created),
    )

    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["version"] == created["version"] + 1
    assert corrected.headers["ETag"] == f'"version-{created["version"] + 1}"'


async def test_the_second_of_two_readings_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Le cas des deux onglets, joué à l'endroit.

    Les deux corrections partent de la même lecture. La première passe ; la
    seconde s'appuie sur une version qui n'existe plus et doit être refusée,
    et non appliquée par-dessus.
    """

    created = await _opportunity(client, default_portfolio_id)
    stale = _if_match(created)

    first = await client.patch(
        f"/api/v1/opportunities/{created['id']}/watch-profile",
        json={"cosmetic_condition": "good", "reason": "Rayures constatées"},
        headers=stale,
    )
    assert first.status_code == 200, first.text

    second = await client.patch(
        f"/api/v1/opportunities/{created['id']}/seller-profile",
        json={"seller_type": "professional", "reason": "Boutique identifiée"},
        headers=stale,
    )

    assert second.status_code == 409, second.text
    error = second.json()["error"]
    assert error["code"] == "RESOURCE_VERSION_CONFLICT"
    assert error["details"]["expected_version"] == created["version"]
    assert error["details"]["current_version"] == created["version"] + 1

    # Et surtout : la première correction est toujours là.
    read = await client.get(f"/api/v1/opportunities/{created['id']}")
    assert read.json()["watch"]["condition_data"]["cosmetic"] == "good"
    assert read.json()["seller"]["seller_type"] == "private"


async def test_two_simultaneous_corrections_leave_one_winner(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Départ simultané : aucune des deux ne peut voir l'autre en lisant.

    C'est le `where version = …` de l'`UPDATE` qui tranche, pas la comparaison
    préalable — celle-ci passerait pour les deux.
    """

    created = await _opportunity(client, default_portfolio_id)
    stale = _if_match(created)

    first, second = await asyncio.gather(
        client.patch(
            f"/api/v1/opportunities/{created['id']}/watch-profile",
            json={"cosmetic_condition": "good", "reason": "Rayures constatées"},
            headers=stale,
        ),
        client.patch(
            f"/api/v1/opportunities/{created['id']}/seller-profile",
            json={"seller_type": "professional", "reason": "Boutique identifiée"},
            headers=stale,
        ),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 409], (
        first.text,
        second.text,
    )
    refused = first if first.status_code == 409 else second
    error = refused.json()["error"]
    assert error["code"] == "RESOURCE_VERSION_CONFLICT"
    # Deux origines possibles selon l'ordonnancement : le contrôle préalable si
    # la perdante lit après le commit de la gagnante, la base si elle a lu
    # avant. Sur ce banc c'est la seconde qui joue — `concurrent_write` — et
    # c'est bien celle qu'on veut voir tenir : le contrôle préalable, seul,
    # laisserait passer.
    assert (
        error["details"].get("reason") == "concurrent_write"
        or error["details"].get("current_version") == created["version"] + 1
    )

    read = await client.get(f"/api/v1/opportunities/{created['id']}")
    assert read.json()["version"] == created["version"] + 1


async def test_a_correction_without_if_match_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Omettre l'en-tête ne doit pas valoir laissez-passer.

    Accepter une correction qui ne dit pas sur quelle version elle s'appuie,
    c'est exactement le comportement que cette protection remplace.
    """

    created = await _opportunity(client, default_portfolio_id)

    response = await client.patch(
        f"/api/v1/opportunities/{created['id']}/watch-profile",
        json={"cosmetic_condition": "good", "reason": "Rayures constatées"},
    )

    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "RESOURCE_VERSION_CONFLICT"
    assert error["details"]["reason"] == "if_match_required"

    # Rien n'a été écrit.
    read = await client.get(f"/api/v1/opportunities/{created['id']}")
    assert read.json()["watch"]["condition_data"]["cosmetic"] != "good"


@pytest.mark.parametrize("value", ["*", "version-3", '"3"', '"version-x"', "W/x"])
async def test_a_malformed_if_match_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID, value: str
) -> None:
    """`*` compris : « n'importe quelle version » est l'écrasement aveugle."""

    created = await _opportunity(client, default_portfolio_id)

    response = await client.patch(
        f"/api/v1/opportunities/{created['id']}/watch-profile",
        json={"cosmetic_condition": "good", "reason": "Rayures constatées"},
        headers={"If-Match": value},
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_a_status_change_also_moves_the_version(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Une transition change le dossier : une correction lue avant doit
    être refusée après."""

    created = await _opportunity(client, default_portfolio_id)
    stale = _if_match(created)

    changed = await client.post(
        f"/api/v1/opportunities/{created['id']}/status",
        json={"status": "buy", "reason": "Affaire retenue après analyse."},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] > created["version"]
    assert changed.headers["ETag"] == f'"version-{changed.json()["version"]}"'

    refused = await client.patch(
        f"/api/v1/opportunities/{created['id']}/watch-profile",
        json={"cosmetic_condition": "good", "reason": "Rayures constatées"},
        headers=stale,
    )
    assert refused.status_code == 409, refused.text
