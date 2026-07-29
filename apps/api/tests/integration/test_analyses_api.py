from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _opportunity(
    client: AsyncClient, portfolio_id: uuid.UUID, ref: str, price: str = "2400.00"
) -> dict:
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
                "originality": "original",
                "box": True,
                "papers": True,
            },
            "seller": {"country_code": "FR", "seller_type": "private"},
            "price": {"amount": price, "currency": "EUR"},
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()

    # La référence ne peut pas être déclarée confirmée à la création : c'est une
    # décision tracée, prise après coup. La porte d'identification la lit.
    confirmed = await client.post(
        f"/api/v1/opportunities/{created['id']}/reference-confirmations",
        json={
            "status": "confirmed",
            "reference_id": created["watch"]["reference_id"],
            "reason": "Référence vérifiée sur les photos du cadran et du fond.",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


async def _comparable(
    client: AsyncClient, opportunity_id: str, amount: str, seller: str
) -> None:
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/comparables",
        json={
            "source_name": "Chrono24",
            "seller_fingerprint": seller,
            "price_kind": "asking",
            "amount": amount,
            "currency": "EUR",
            "market_status": "active",
            "observed_at": (datetime.now(UTC) - timedelta(days=5)).isoformat(),
            "source_reliability": "a",
            "mechanical_condition": "verified",
            "cosmetic_condition": "excellent",
            "box": True,
            "papers": True,
        },
    )
    assert response.status_code == 201, response.text


async def _market(client: AsyncClient, opportunity_id: str) -> dict:
    """Six comparables serrés autour de 3 600 € : une cote solide, pour que le
    test porte sur l'analyse et non sur la qualité du marché."""

    for index, amount in enumerate(
        ["3500.00", "3550.00", "3600.00", "3620.00", "3680.00", "3700.00"]
    ):
        await _comparable(client, opportunity_id, amount, seller=f"s{index}")

    response = await client.post(f"/api/v1/opportunities/{opportunity_id}/valuations")
    assert response.status_code == 201, response.text
    return response.json()


async def _fund(db_session: AsyncSession, portfolio_id: uuid.UUID, amount: str) -> None:
    await db_session.execute(
        text(
            """
            insert into portfolio_ledger_entries (
              portfolio_id, kind, amount_source, currency, amount_eur,
              rate_to_eur, fx_rate_at, fx_source, occurred_at, actor_user_id
            )
            select :portfolio_id, 'capital_contribution', :amount, 'EUR', :amount,
                   1, now(), 'saisie manuelle', now(), id
            from users limit 1
            """
        ),
        {"portfolio_id": portfolio_id, "amount": amount},
    )
    await db_session.commit()


# --- Préconditions -------------------------------------------------------


async def test_an_analysis_without_a_quote_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Le score dépend de la cote : l'estimer en son absence reviendrait à
    inventer un marché."""

    opportunity = await _opportunity(client, default_portfolio_id, "ANA-001")

    response = await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    assert response.status_code == 422
    assert "cote" in response.json()["error"]["message"].lower()


async def test_an_unknown_opportunity_is_not_found(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    response = await client.post(f"/api/v1/opportunities/{uuid.uuid4()}/analyses")
    assert response.status_code == 404


# --- Analyse nominale ----------------------------------------------------


async def test_an_analysis_carries_its_whole_reasoning(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Règle 6 : une recommandation expose ses entrées, ses règles, ses
    versions, ses plafonds et ses motifs."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "ANA-002")
    await _market(client, opportunity["id"])

    response = await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["state"] == "published"
    assert body["recommendation"] in {"buy", "watch", "pass", "analysis_impossible"}
    assert len(body["gates"]) == 5
    assert body["pillars"] is not None
    assert set(body["scenario_results"]) == {"prudent", "central", "favorable"}
    assert body["explanation"]["ruleset_version"]
    assert body["explanation"]["max_purchase"]["binding_constraint"]
    assert body["explanation"]["sale_delay"]["days"] > 0
    assert body["explanation"]["record"]["score"]
    assert body["strategy_snapshot"]["minimum_roi"]
    assert body["portfolio_snapshot"]["available_cash_eur"] == "20000.00"


async def test_amounts_and_scores_travel_as_decimal_strings(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Un score ou un ROI en flottant perdrait la valeur exacte qui a été
    figée."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "ANA-003")
    await _market(client, opportunity["id"])

    body = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()

    for field in (
        "current_price_eur",
        "expected_profit_eur",
        "expected_roi",
        "score",
        "max_purchase_price_eur",
    ):
        assert isinstance(body[field], str), field


async def test_the_ruleset_snapshot_is_never_served(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Le barème figé pèse près d'un mégaoctet et n'a d'intérêt qu'au rejeu :
    sa version suffit à l'identifier."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "ANA-004")
    await _market(client, opportunity["id"])

    body = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()

    assert "ruleset_snapshot" not in body
    assert body["explanation"]["ruleset_version"]


# --- Immuabilité ---------------------------------------------------------


async def test_recalculation_chains_a_new_version(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Une analyse est immuable : un recalcul crée une version chaînée à la
    précédente plutôt que de l'écraser (règle 4)."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "ANA-005")
    await _market(client, opportunity["id"])

    first = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()
    second = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()

    assert first["id"] != second["id"]

    previous = (
        await db_session.execute(
            text("select previous_analysis_id from analyses where id = :id"),
            {"id": second["id"]},
        )
    ).scalar_one()
    assert str(previous) == first["id"]


async def test_the_latest_analysis_is_the_most_recent_one(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "ANA-006")
    await _market(client, opportunity["id"])

    await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    second = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()

    latest = await client.get(
        f"/api/v1/opportunities/{opportunity['id']}/analyses/latest"
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == second["id"]


async def test_a_frozen_analysis_cannot_be_updated(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """L'immuabilité tient au niveau de la base, pas seulement du code."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "ANA-007")
    await _market(client, opportunity["id"])

    body = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()

    with pytest.raises(Exception) as excinfo:
        await db_session.execute(
            text("update analyses set score = 100 where id = :id"),
            {"id": body["id"]},
        )
        await db_session.commit()
    assert "IMMUTABLE_RESOURCE" in str(excinfo.value)
    await db_session.rollback()


# --- Portefeuille --------------------------------------------------------


async def test_a_portfolio_without_cash_cannot_be_analysed(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Sans trésorerie, l'allocation n'a pas de sens : mieux vaut refuser que
    produire un taux de convention."""

    opportunity = await _opportunity(client, default_portfolio_id, "ANA-008")
    await _market(client, opportunity["id"])

    response = await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    assert response.status_code == 422


async def test_adding_capital_changes_the_verdict(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """L'apport de capital en cours de route doit débloquer la capacité
    d'achat, sans qu'on retouche l'historique."""

    await _fund(db_session, default_portfolio_id, "3000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "ANA-009")
    await _market(client, opportunity["id"])

    tight = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()

    await _fund(db_session, default_portfolio_id, "30000.00")
    roomy = (
        await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    ).json()

    assert roomy["portfolio_snapshot"]["available_cash_eur"] == "33000.00"
    # Même affaire, même marché : seule l'allocation a changé.
    assert (
        roomy["portfolio_snapshot"]["allocation_rate"]
        < (tight["portfolio_snapshot"]["allocation_rate"])
    )
    assert roomy["score"] >= tight["score"]
