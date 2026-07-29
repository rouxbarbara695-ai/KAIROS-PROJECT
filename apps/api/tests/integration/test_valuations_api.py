from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config import get_settings

pytestmark = pytest.mark.integration


async def _opportunity(client: AsyncClient, portfolio_id: uuid.UUID, ref: str) -> dict:
    response = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(portfolio_id),
            "source": {"mode": "manual", "manual_identifier": ref},
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


async def _add(
    client: AsyncClient,
    opportunity_id: str,
    amount: str,
    *,
    reliability: str = "a",
    seller: str | None = None,
    age_days: int = 5,
    box: bool = True,
    papers: bool = True,
) -> str:
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/comparables",
        json={
            "source_name": "Chrono24",
            "seller_fingerprint": seller,
            "price_kind": "asking",
            "amount": amount,
            "currency": "EUR",
            "market_status": "active",
            "observed_at": (datetime.now(UTC) - timedelta(days=age_days)).isoformat(),
            "source_reliability": reliability,
            "mechanical_condition": "verified",
            "cosmetic_condition": "excellent",
            "box": box,
            "papers": papers,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_valuation_requires_enough_comparables(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _opportunity(client, default_portfolio_id, "VAL-001")
    await _add(client, opportunity["id"], "3000.00", seller="s1")

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/valuations"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALUATION_INSUFFICIENT_COMPARABLES"


async def test_valuation_is_computed_and_traced(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _opportunity(client, default_portfolio_id, "VAL-002")
    for index, amount in enumerate(["3000.00", "3100.00", "3200.00", "3300.00"]):
        await _add(client, opportunity["id"], amount, seller=f"s{index}")

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/valuations"
    )
    assert response.status_code == 201, response.text
    body = response.json()

    low = body["low_value_eur"]
    central = body["central_value_eur"]
    high = body["high_value_eur"]
    assert low <= central <= high

    explanation = body["explanation"]
    # Rattaché au barème actif, pas à une version en dur : figer « 1.0.0 » ici
    # ferait échouer le test à chaque nouveau ruleset alors que le
    # comportement vérifié — la cote porte sa version — n'a pas changé.
    assert explanation["ruleset_version"] == get_settings().active_ruleset_version
    assert explanation["comparables_used"] == 4
    assert explanation["target_completeness"] == "full_set"
    assert "confidence" in explanation
    assert isinstance(body["valuation_confidence"], str)


async def test_identity_not_confirmed_caps_confidence(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """La référence n'ayant pas été confirmée, le plafond correspondant doit
    figurer dans la trace et contenir la confiance."""

    opportunity = await _opportunity(client, default_portfolio_id, "VAL-003")
    for index, amount in enumerate(["3000.00", "3100.00", "3200.00", "3300.00"]):
        await _add(client, opportunity["id"], amount, seller=f"s{index}")

    body = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/valuations")
    ).json()

    caps = [cap["name"] for cap in body["explanation"]["confidence"]["applied_caps"]]
    assert "identity_unconfirmed" in caps
    assert float(body["valuation_confidence"]) <= 40


async def test_excluded_comparable_is_not_used_but_is_recorded(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Un comparable exclu ne participe pas au calcul, mais reste figé dans la
    trace : la cote doit rester rejouable, exclusions comprises."""

    opportunity = await _opportunity(client, default_portfolio_id, "VAL-004")
    ids = []
    for index, amount in enumerate(["3000.00", "3100.00", "3200.00", "9900.00"]):
        ids.append(await _add(client, opportunity["id"], amount, seller=f"s{index}"))

    await client.post(
        f"/api/v1/comparables/{ids[-1]}/overrides",
        json={
            "excluded": True,
            "exclusion_reason": "Montre repeinte",
            "reason": "Photos incohérentes",
        },
    )

    body = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/valuations")
    ).json()

    assert body["explanation"]["comparables_total"] == 4
    assert body["explanation"]["comparables_excluded_by_user"] == 1
    assert body["explanation"]["comparables_used"] == 3

    rows = (
        await db_session.execute(
            text(
                "select count(*) from valuation_comparables "
                "where valuation_id = :valuation_id"
            ),
            {"valuation_id": body["id"]},
        )
    ).scalar_one()
    assert rows == 4


async def test_recalculation_creates_a_new_immutable_version(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _opportunity(client, default_portfolio_id, "VAL-005")
    for index, amount in enumerate(["3000.00", "3100.00", "3200.00"]):
        await _add(client, opportunity["id"], amount, seller=f"s{index}")

    first = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/valuations")
    ).json()
    second = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/valuations")
    ).json()

    assert first["id"] != second["id"]

    count = (
        await db_session.execute(
            text(
                "select count(*) from market_valuations "
                "where opportunity_id = :opportunity_id"
            ),
            {"opportunity_id": opportunity["id"]},
        )
    ).scalar_one()
    assert count == 2

    with pytest.raises(Exception) as exc:
        await db_session.execute(
            text("update market_valuations set central_value_eur = 1 where id = :id"),
            {"id": first["id"]},
        )
        await db_session.commit()
    assert "IMMUTABLE_RESOURCE" in str(exc.value)
    await db_session.rollback()


async def test_single_seller_caps_confidence(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _opportunity(client, default_portfolio_id, "VAL-006")
    for amount in ["3000.00", "3100.00", "3200.00", "3300.00"]:
        await _add(client, opportunity["id"], amount, seller="unique-seller")

    body = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/valuations")
    ).json()

    caps = [cap["name"] for cap in body["explanation"]["confidence"]["applied_caps"]]
    assert "single_seller" in caps


async def test_valuation_of_foreign_opportunity_is_not_disclosed(
    client: AsyncClient,
) -> None:
    response = await client.post(f"/api/v1/opportunities/{uuid.uuid4()}/valuations")
    assert response.status_code == 404
