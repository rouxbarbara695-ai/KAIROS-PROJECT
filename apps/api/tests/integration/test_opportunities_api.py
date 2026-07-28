import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def _create_longines(client: AsyncClient, portfolio_id: uuid.UUID) -> dict:
    response = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(portfolio_id),
            "source": {"mode": "manual", "manual_identifier": "LONGINES-2026-001"},
            "watch": {
                "brand": "Longines",
                "reference": "L2.257.4.57.6",
                "mechanical_condition": "functional",
                "cosmetic_condition": "excellent",
                "box": True,
                "papers": True,
            },
            "seller": {"country_code": "FR", "seller_type": "private"},
            "price": {"amount": "1800.00", "currency": "EUR"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_manual_opportunity_without_listing(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    body = await _create_longines(client, default_portfolio_id)
    assert body["source_mode"] == "manual"
    assert body["manual_identifier"] == "LONGINES-2026-001"
    assert body["status"] == "watching"
    assert body["watch"]["brand"] == "Longines"
    assert body["latest_price"]["amount"] == "1800.00"
    assert body["latest_price"]["amount_eur"] == "1800.00"


async def test_price_amount_is_json_string_not_number(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    response = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {"mode": "manual", "manual_identifier": "REJECT-FLOAT"},
            "watch": {"brand": "Omega", "reference": "REF-X"},
            "price": {"amount": 1800.0, "currency": "EUR"},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_missing_price_never_defaults_to_zero(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    response = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {"mode": "manual", "manual_identifier": "NO-PRICE"},
            "watch": {"brand": "Omega", "reference": "REF-Y"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["latest_price"]["amount"] is None
    assert body["latest_price"]["missing_reason"] is not None


async def test_duplicate_manual_identifier_returns_409(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    first = await _create_longines(client, default_portfolio_id)
    response = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {"mode": "manual", "manual_identifier": "LONGINES-2026-001"},
            "watch": {"brand": "Longines", "reference": "L2.257.4.57.6"},
        },
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "OPPORTUNITY_DUPLICATE"
    assert error["details"]["matched_on"] == "manual_identifier"
    assert error["details"]["existing_opportunity_id"] == first["id"]


async def test_duplicate_url_ignoring_tracking_params_returns_409(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    first = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {
                "mode": "url",
                "url": "https://www.chrono24.fr/longines/l2257457-6.htm?utm_source=x",
            },
            "watch": {"brand": "Longines", "reference": "L2.257.4.57.6"},
        },
    )
    assert first.status_code == 201, first.text

    duplicate = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {
                "mode": "url",
                "url": "https://chrono24.fr/longines/l2257457-6.htm?gclid=y",
            },
            "watch": {"brand": "Longines", "reference": "L2.257.4.57.6"},
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"]["matched_on"] == "canonical_url"


async def test_get_unknown_opportunity_returns_404_not_403(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    response = await client.get(f"/api/v1/opportunities/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_creating_opportunity_in_foreign_portfolio_is_forbidden(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    foreign_portfolio_id = uuid.uuid4()
    response = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(foreign_portfolio_id),
            "source": {"mode": "manual", "manual_identifier": "HACK"},
            "watch": {"brand": "Rolex", "reference": "116500LN"},
        },
    )
    assert response.status_code == 403


async def test_unrecognized_condition_falls_back_to_prudent_value(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    response = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {"mode": "manual", "manual_identifier": "WEIRD-COND"},
            "watch": {
                "brand": "Omega",
                "reference": "REF-Z",
                "cosmetic_condition": "brand_new_never_worn",
            },
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["watch"]["condition_data"]["cosmetic"] == "poor"


async def test_reference_confirmation_requires_reference_id_when_confirming(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    created = await _create_longines(client, default_portfolio_id)
    response = await client.post(
        f"/api/v1/opportunities/{created['id']}/reference-confirmations",
        json={"status": "confirmed", "reason": "test"},
    )
    assert response.status_code == 422


async def test_reference_confirmation_updates_status_and_audits(
    client: AsyncClient, default_portfolio_id: uuid.UUID, db_session
) -> None:
    from sqlalchemy import text

    created = await _create_longines(client, default_portfolio_id)
    reference_id = (
        await db_session.execute(text("select reference_id from watches limit 1"))
    ).scalar_one()

    response = await client.post(
        f"/api/v1/opportunities/{created['id']}/reference-confirmations",
        json={
            "status": "confirmed",
            "reference_id": str(reference_id),
            "reason": "Référence visible sur les papiers",
        },
    )
    assert response.status_code == 200
    assert response.json()["watch"]["reference_status"] == "confirmed"

    audit_count = (
        await db_session.execute(
            text("select count(*) from audit_events where resource_type='watch'")
        )
    ).scalar_one()
    assert audit_count == 1


async def test_watch_profile_patch_requires_reason(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    created = await _create_longines(client, default_portfolio_id)
    response = await client.patch(
        f"/api/v1/opportunities/{created['id']}/watch-profile",
        json={"cosmetic_condition": "good"},
    )
    assert response.status_code == 422


async def test_watch_profile_patch_updates_and_audits(
    client: AsyncClient, default_portfolio_id: uuid.UUID, db_session
) -> None:
    from sqlalchemy import text

    created = await _create_longines(client, default_portfolio_id)
    response = await client.patch(
        f"/api/v1/opportunities/{created['id']}/watch-profile",
        json={"cosmetic_condition": "good", "reason": "Nouvelles photos"},
    )
    assert response.status_code == 200
    assert response.json()["watch"]["condition_data"]["cosmetic"] == "good"

    audit_count = (
        await db_session.execute(text("select count(*) from audit_events"))
    ).scalar_one()
    assert audit_count == 1


async def test_seller_profile_patch(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    created = await _create_longines(client, default_portfolio_id)
    response = await client.patch(
        f"/api/v1/opportunities/{created['id']}/seller-profile",
        json={"seller_type": "professional", "reason": "Vendeur identifié marchand"},
    )
    assert response.status_code == 200
    assert response.json()["seller"]["seller_type"] == "professional"


async def test_add_price_input_creates_dated_entry(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    created = await _create_longines(client, default_portfolio_id)
    response = await client.post(
        f"/api/v1/opportunities/{created['id']}/price-inputs",
        json={"kind": "offer", "amount": "1700.00", "currency": "EUR"},
    )
    assert response.status_code == 201


async def test_list_opportunities_filters_by_brand(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    await _create_longines(client, default_portfolio_id)
    response = await client.get("/api/v1/opportunities", params={"brand": "Longines"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["watch"]["brand"] == "Longines"

    empty = await client.get("/api/v1/opportunities", params={"brand": "Nonexistent"})
    assert empty.json()["items"] == []


async def test_patch_opportunity_whitelist_requires_reason(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    created = await _create_longines(client, default_portfolio_id)
    response = await client.patch(
        f"/api/v1/opportunities/{created['id']}",
        json={},
    )
    assert response.status_code == 422


async def test_patch_opportunity_unknown_strategy_rejected(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    created = await _create_longines(client, default_portfolio_id)
    response = await client.patch(
        f"/api/v1/opportunities/{created['id']}",
        json={"strategy_id": str(uuid.uuid4()), "reason": "test"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "strategy_id"


async def test_patch_opportunity_selects_own_strategy(
    client: AsyncClient, default_portfolio_id: uuid.UUID, db_session
) -> None:
    from sqlalchemy import text

    created = await _create_longines(client, default_portfolio_id)
    strategy_id = uuid.uuid4()
    await db_session.execute(
        text(
            "insert into strategies (id, portfolio_id, name, created_by_user_id) "
            "select :id, :portfolio_id, 'défaut', created_by_user_id "
            "from opportunities where id = :opportunity_id"
        ),
        {
            "id": strategy_id,
            "portfolio_id": default_portfolio_id,
            "opportunity_id": created["id"],
        },
    )
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/opportunities/{created['id']}",
        json={"strategy_id": str(strategy_id), "reason": "Stratégie choisie"},
    )
    assert response.status_code == 200

    audit_count = (
        await db_session.execute(
            text("select count(*) from audit_events where resource_type='opportunity'")
        )
    ).scalar_one()
    assert audit_count == 1


async def test_get_platform_rules_returns_applicable_rule(
    client: AsyncClient, db_session
) -> None:
    from sqlalchemy import text

    platform_code = (
        await db_session.execute(text("select code from platforms limit 1"))
    ).scalar_one()
    await db_session.execute(
        text(
            "insert into platform_rules (platform_id, region_code, version, "
            "valid_from, buyer_fee_rate) "
            "select id, '*', 1, '2020-01-01', 0.05 from platforms where code=:code"
        ),
        {"code": platform_code},
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/platforms/{platform_code}/rules")
    assert response.status_code == 200
    body = response.json()
    assert body["platform_code"] == platform_code
    assert body["access_authorized"] is False
    assert body["buyer_fee_rate"] == "0.0500000000"


async def test_get_platform_rules_unknown_platform_returns_404(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/platforms/does-not-exist/rules")
    assert response.status_code == 404


async def test_get_platform_rules_no_applicable_rule_returns_404(
    client: AsyncClient, db_session
) -> None:
    from sqlalchemy import text

    platform_code = (
        await db_session.execute(text("select code from platforms limit 1 offset 1"))
    ).scalar_one()
    response = await client.get(f"/api/v1/platforms/{platform_code}/rules")
    assert response.status_code == 404
