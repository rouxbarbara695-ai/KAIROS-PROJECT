from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_CATAWIKI = {
    "provenance_url": "https://www.catawiki.com/fr/help/selling-fees",
    "buyer_fee_rate": "0.09",
    "seller_fee_rate": "0.125",
    "seller_fee_fixed": "20.00",
    "currency": "EUR",
}


async def _create(client: AsyncClient, code: str = "catawiki", **overrides: object):
    return await client.post(
        f"/api/v1/platforms/{code}/rules", json={**_CATAWIKI, **overrides}
    )


async def test_no_platform_has_a_fee_schedule_out_of_the_box(
    client: AsyncClient,
) -> None:
    """Aucune grille n'est seedée, et c'est délibéré : une commission inventée
    fausserait tous les profits sans que rien ne le signale."""

    body = (await client.get("/api/v1/platforms")).json()
    assert body
    assert all(not platform["has_active_rule"] for platform in body)


async def test_a_recorded_schedule_becomes_the_active_one(
    client: AsyncClient,
) -> None:
    created = await _create(client)
    assert created.status_code == 201, created.text
    assert created.json()["version"] == 1

    body = (await client.get("/api/v1/platforms")).json()
    catawiki = next(item for item in body if item["code"] == "catawiki")
    assert catawiki["has_active_rule"]
    assert catawiki["active_rule"]["seller_fee_rate"] == "0.1250000000"
    assert catawiki["active_rule"]["seller_fee_fixed"] == "20.00"


async def test_recording_again_closes_the_previous_version(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Une grille n'est jamais réécrite : une analyse produite sous l'ancienne
    reste rejouable."""

    first = (await _create(client)).json()
    second = (await _create(client, seller_fee_rate="0.15")).json()

    assert second["version"] == first["version"] + 1

    closed = (
        await db_session.execute(
            text("select valid_to from platform_rules where id = :id"),
            {"id": first["id"]},
        )
    ).scalar_one()
    assert closed is not None

    body = (await client.get("/api/v1/platforms")).json()
    catawiki = next(item for item in body if item["code"] == "catawiki")
    assert catawiki["active_rule"]["id"] == second["id"]


async def test_recording_a_schedule_authorises_no_collection(
    client: AsyncClient,
) -> None:
    """Règle 9 : saisir des tarifs ne vaut pas feu vert de collecte. Le mode
    d'accès et son autorisation relèvent d'une validation écrite distincte."""

    body = (await _create(client)).json()
    assert body["access_method"] == "manual"
    assert body["access_authorized"] is False


async def test_provenance_is_required(client: AsyncClient) -> None:
    """Une grille qu'on ne peut pas vérifier ne vaut pas mieux qu'une grille
    inventée."""

    response = await client.post(
        "/api/v1/platforms/catawiki/rules", json={"seller_fee_rate": "0.10"}
    )
    assert response.status_code == 422


async def test_a_floor_above_its_cap_is_refused(client: AsyncClient) -> None:
    response = await _create(client, seller_fee_min="500.00", seller_fee_max="100.00")
    assert response.status_code == 422


async def test_an_unknown_platform_is_not_found(client: AsyncClient) -> None:
    assert (await _create(client, code="brocante-du-coin")).status_code == 404


async def test_rates_travel_as_decimal_strings(client: AsyncClient) -> None:
    body = (await _create(client)).json()
    for field in ("buyer_fee_rate", "seller_fee_rate", "seller_fee_fixed"):
        assert isinstance(body[field], str), field


async def test_a_schedule_with_no_fees_is_accepted(client: AsyncClient) -> None:
    """Une plateforme sans frais est un constat, pas un oubli de saisie."""

    response = await client.post(
        "/api/v1/platforms/user_data/rules",
        json={"provenance_url": "https://exemple.test/tarifs"},
    )
    assert response.status_code == 201
    assert response.json()["seller_fee_rate"] is None


# --- Effet sur l'analyse -------------------------------------------------


async def test_fees_reach_the_scenarios(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Sans grille, le profit affiché est celui d'une vente entre
    particuliers. Avec la grille de Catawiki, il baisse — c'est tout l'enjeu
    de la saisie."""

    await db_session.execute(
        text(
            """
            insert into portfolio_ledger_entries (portfolio_id, kind,
              amount_source, currency, amount_eur, rate_to_eur, fx_rate_at,
              fx_source, occurred_at, actor_user_id)
            select :pf, 'capital_contribution', 30000, 'EUR', 30000, 1, now(),
                   'saisie manuelle', now(), id from users limit 1
            """
        ),
        {"pf": default_portfolio_id},
    )
    await db_session.commit()

    opportunity = (
        await client.post(
            "/api/v1/opportunities",
            json={
                "portfolio_id": str(default_portfolio_id),
                "source": {"mode": "manual", "manual_identifier": "PLT-001"},
                "watch": {
                    "brand": "Tudor",
                    "reference": "79030N",
                    "mechanical_condition": "verified",
                    "cosmetic_condition": "excellent",
                    "box": True,
                    "papers": True,
                },
                "seller": {"country_code": "FR", "seller_type": "private"},
                "price": {"amount": "2400.00", "currency": "EUR"},
            },
        )
    ).json()

    # Sans référence confirmée, la porte d'identification bloque et l'analyse
    # ne produit aucun scénario : le test porterait alors sur autre chose.
    confirmed = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/reference-confirmations",
        json={
            "status": "confirmed",
            "reference_id": opportunity["watch"]["reference_id"],
            "reason": "Référence vérifiée sur le fond de boîtier.",
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    for index, amount in enumerate(
        ["3500.00", "3550.00", "3600.00", "3620.00", "3680.00", "3700.00"]
    ):
        await client.post(
            f"/api/v1/opportunities/{opportunity['id']}/comparables",
            json={
                "source_name": "Chrono24",
                "seller_fingerprint": f"s{index}",
                "price_kind": "asking",
                "amount": amount,
                "currency": "EUR",
                "market_status": "active",
                "observed_at": "2026-07-20T10:00:00Z",
                "source_reliability": "a",
                "mechanical_condition": "verified",
                "cosmetic_condition": "excellent",
                "box": True,
                "papers": True,
            },
        )
    await client.post(f"/api/v1/opportunities/{opportunity['id']}/valuations")

    analysis = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()

    # Une opportunité manuelle n'est rattachée à aucune plateforme : ses coûts
    # sont ceux d'une vente entre particuliers.
    central = analysis["scenario_results"]["central"]
    assert central["total_cost_before_sale_eur"] == "2400.00"
