from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def _confirmed_opportunity(
    client: AsyncClient, portfolio_id: uuid.UUID, identifier: str
) -> dict:
    """Une opportunité dont la référence est confirmée : un comparable doit se
    rattacher à une référence identifiée."""

    response = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(portfolio_id),
            "source": {"mode": "manual", "manual_identifier": identifier},
            "watch": {
                "brand": "Tudor",
                "reference": "79030N",
                "mechanical_condition": "verified",
                "cosmetic_condition": "excellent",
                "box": True,
                "papers": True,
            },
            "seller": {"country_code": "FR", "seller_type": "private"},
            "price": {"amount": "3200.00", "currency": "EUR"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _comparable_payload(**overrides: object) -> dict:
    payload: dict = {
        "source_name": "Chrono24",
        "price_kind": "asking",
        "amount": "3500.00",
        "currency": "EUR",
        "market_status": "active",
        "observed_at": datetime.now(UTC).isoformat(),
        "source_reliability": "c",
        "mechanical_condition": "functional",
        "cosmetic_condition": "very_good",
        "box": True,
        "papers": False,
    }
    payload.update(overrides)
    return payload


async def test_create_comparable_freezes_buyer_cost(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _confirmed_opportunity(client, default_portfolio_id, "CMP-001")

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/comparables",
        json=_comparable_payload(
            buyer_variable_fee_eur="200.00",
            buyer_fixed_fee_eur="15.00",
            compulsory_shipping_eur="30.00",
        ),
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["amount_eur"] == "3500.00"
    assert body["buyer_total_price_eur"] == "3745.00"
    assert body["excluded"] is False
    assert body["completeness_data"]["level"] == "box_or_papers"


async def test_amounts_are_json_strings(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _confirmed_opportunity(client, default_portfolio_id, "CMP-002")
    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/comparables",
        json=_comparable_payload(),
    )
    assert isinstance(response.json()["amount_eur"], str)


async def test_numeric_amount_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Un montant transmis comme nombre JSON perdrait sa précision décimale."""

    opportunity = await _confirmed_opportunity(client, default_portfolio_id, "CMP-003")
    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/comparables",
        json=_comparable_payload(amount=3500.00),
    )
    assert response.status_code == 422


async def test_unknown_currency_without_rate_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _confirmed_opportunity(client, default_portfolio_id, "CMP-004")
    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/comparables",
        json=_comparable_payload(currency="JPY"),
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "FX_RATE_UNAVAILABLE"


async def test_end_before_listing_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _confirmed_opportunity(client, default_portfolio_id, "CMP-005")
    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/comparables",
        json=_comparable_payload(
            listed_at="2026-06-01T00:00:00Z", ended_at="2026-05-01T00:00:00Z"
        ),
    )
    assert response.status_code == 422


async def test_foreign_opportunity_is_not_disclosed(client: AsyncClient) -> None:
    response = await client.post(
        f"/api/v1/opportunities/{uuid.uuid4()}/comparables",
        json=_comparable_payload(),
    )
    assert response.status_code == 404


# --- Overrides -----------------------------------------------------------


async def test_exclusion_requires_its_own_reason(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _confirmed_opportunity(client, default_portfolio_id, "CMP-010")
    created = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/comparables",
        json=_comparable_payload(),
    )
    comparable_id = created.json()["id"]

    response = await client.post(
        f"/api/v1/comparables/{comparable_id}/overrides",
        json={"excluded": True, "reason": "Audit"},
    )
    assert response.status_code == 422


async def test_exclusion_then_reinstatement_chains_and_audits(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Rien n'est modifié ni supprimé : chaque décision ajoute un maillon qui
    référence le précédent, et l'état courant est le dernier de la chaîne."""

    opportunity = await _confirmed_opportunity(client, default_portfolio_id, "CMP-011")
    created = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/comparables",
        json=_comparable_payload(),
    )
    comparable_id = created.json()["id"]

    excluded = await client.post(
        f"/api/v1/comparables/{comparable_id}/overrides",
        json={
            "excluded": True,
            "exclusion_reason": "Montre repeinte",
            "reason": "Photos incohérentes",
        },
    )
    assert excluded.status_code == 201, excluded.text
    first = excluded.json()
    assert first["previous_override_id"] is None

    listed = await client.get(f"/api/v1/opportunities/{opportunity['id']}/comparables")
    assert listed.json()["items"][0]["excluded"] is True
    assert listed.json()["items"][0]["exclusion_reason"] == "Montre repeinte"

    reinstated = await client.post(
        f"/api/v1/comparables/{comparable_id}/overrides",
        json={"excluded": False, "reason": "Vendeur a fourni les papiers"},
    )
    assert reinstated.status_code == 201
    assert reinstated.json()["previous_override_id"] == first["id"]

    listed = await client.get(f"/api/v1/opportunities/{opportunity['id']}/comparables")
    assert listed.json()["items"][0]["excluded"] is False

    events = await client.get(f"/api/v1/opportunities/{opportunity['id']}/events")
    actions = [event["action"] for event in events.json()["items"]]
    assert "exclude" in actions
    assert "reinstate" in actions


async def test_override_on_foreign_comparable_is_not_disclosed(
    client: AsyncClient,
) -> None:
    response = await client.post(
        f"/api/v1/comparables/{uuid.uuid4()}/overrides",
        json={"excluded": False, "reason": "Test"},
    )
    assert response.status_code == 404


async def test_comparables_are_scoped_to_the_reference(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Deux opportunités portant la même référence partagent leurs comparables :
    la cote appartient à la référence, pas à l'annonce."""

    first = await _confirmed_opportunity(client, default_portfolio_id, "CMP-020")
    second = await _confirmed_opportunity(client, default_portfolio_id, "CMP-021")

    await client.post(
        f"/api/v1/opportunities/{first['id']}/comparables",
        json=_comparable_payload(),
    )

    listed = await client.get(f"/api/v1/opportunities/{second['id']}/comparables")
    assert len(listed.json()["items"]) == 1
