from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _opportunity(client: AsyncClient, portfolio_id: uuid.UUID, ref: str) -> dict:
    created = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(portfolio_id),
            "source": {"mode": "manual", "manual_identifier": ref},
            "watch": {"brand": "Tudor", "reference": "79030N"},
            "seller": {"country_code": "FR", "seller_type": "private"},
            "price": {"amount": "2400.00", "currency": "EUR"},
        },
    )
    assert created.status_code == 201, created.text
    body: dict = created.json()
    return body


async def _intend_to_buy(client: AsyncClient, opportunity_id: str) -> None:
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/status",
        json={"status": "buy", "reason": "Affaire retenue après analyse."},
    )
    assert response.status_code == 200, response.text


async def _fund(db_session: AsyncSession, portfolio_id: uuid.UUID) -> None:
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
        {"pf": portfolio_id},
    )
    await db_session.commit()


async def test_recording_a_purchase_moves_cash_and_stock(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """La boucle se ferme : la trésorerie baisse, le stock monte, et les deux
    viennent du même geste."""

    await _fund(db_session, default_portfolio_id)
    opportunity = await _opportunity(client, default_portfolio_id, "ACH-001")
    await _intend_to_buy(client, opportunity["id"])

    before = (
        await client.get(f"/api/v1/portfolios/{default_portfolio_id}/overview")
    ).json()

    recorded = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/purchase",
        json={
            "amount": "2250.00",
            "currency": "EUR",
            "reason": "Négocié à 2 250 € sur place.",
        },
    )
    assert recorded.status_code == 201, recorded.text

    after = (
        await client.get(f"/api/v1/portfolios/{default_portfolio_id}/overview")
    ).json()

    spent = Decimal(before["available_cash_eur"]) - Decimal(after["available_cash_eur"])
    gained = Decimal(after["stock_at_cost_eur"]) - Decimal(before["stock_at_cost_eur"])
    assert spent == Decimal("2250.00")
    assert gained == Decimal("2250.00")


async def test_the_price_paid_is_not_the_price_asked(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Le prix affiché était de 2 400 € et la négociation l'a ramené à 2 250 €.
    C'est le montant payé qui fait le coût de revient : reprendre le prix
    demandé ferait de KAIROS un outil qui se relit lui-même."""

    await _fund(db_session, default_portfolio_id)
    opportunity = await _opportunity(client, default_portfolio_id, "ACH-002")
    await _intend_to_buy(client, opportunity["id"])

    body = (
        await client.post(
            f"/api/v1/opportunities/{opportunity['id']}/purchase",
            json={
                "amount": "2250.00",
                "currency": "EUR",
                "reason": "Négocié.",
            },
        )
    ).json()
    assert body["amount_eur"] == "2250.00"


async def test_the_treasury_entry_is_written_by_the_purchase(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """`purchase_payment` ne se saisit pas à la main : l'API le refuse. Il doit
    donc exister quelqu'un pour l'écrire, et c'est l'achat."""

    await _fund(db_session, default_portfolio_id)
    opportunity = await _opportunity(client, default_portfolio_id, "ACH-003")
    await _intend_to_buy(client, opportunity["id"])
    await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/purchase",
        json={"amount": "2250.00", "currency": "EUR", "reason": "Acheté."},
    )

    kinds = set(
        (
            await db_session.execute(
                text(
                    "select kind from portfolio_ledger_entries "
                    "where opportunity_id = :id"
                ),
                {"id": opportunity["id"]},
            )
        ).scalars()
    )
    assert kinds == {"purchase_payment"}

    refused = await client.post(
        f"/api/v1/portfolios/{default_portfolio_id}/ledger-entries",
        json={"kind": "purchase_payment", "amount": "100", "currency": "EUR"},
    )
    assert refused.status_code == 422


async def test_a_purchase_needs_the_intention_first(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Une opportunité en veille ne s'achète pas directement : la
    spécification passe par une intention d'achat."""

    await _fund(db_session, default_portfolio_id)
    opportunity = await _opportunity(client, default_portfolio_id, "ACH-004")

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/purchase",
        json={"amount": "2250.00", "currency": "EUR", "reason": "Acheté."},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"


async def test_a_watch_is_not_bought_twice(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    await _fund(db_session, default_portfolio_id)
    opportunity = await _opportunity(client, default_portfolio_id, "ACH-005")
    await _intend_to_buy(client, opportunity["id"])

    payload = {"amount": "2250.00", "currency": "EUR", "reason": "Acheté."}
    first = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/purchase", json=payload
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/purchase", json=payload
    )
    assert second.status_code == 409


async def test_a_purchase_beyond_available_cash_is_recorded_anyway(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Un achat est un fait accompli, à la différence d'un retrait. Refuser de
    l'enregistrer parce que le registre ignore d'où venait l'argent ferait
    mentir l'outil sur ce qu'on possède : la trésorerie négative qui en résulte
    se lit comme un apport oublié."""

    opportunity = await _opportunity(client, default_portfolio_id, "ACH-006")
    await _intend_to_buy(client, opportunity["id"])

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/purchase",
        json={"amount": "2250.00", "currency": "EUR", "reason": "Payé en espèces."},
    )
    assert response.status_code == 201

    overview = (
        await client.get(f"/api/v1/portfolios/{default_portfolio_id}/overview")
    ).json()
    assert Decimal(overview["available_cash_eur"]) < 0


async def test_a_purchase_requires_a_reason(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _opportunity(client, default_portfolio_id, "ACH-007")
    await _intend_to_buy(client, opportunity["id"])

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/purchase",
        json={"amount": "2250.00", "currency": "EUR", "reason": "  "},
    )
    assert response.status_code == 422


async def test_a_purchase_cannot_be_dated_in_the_future(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _opportunity(client, default_portfolio_id, "ACH-008")
    await _intend_to_buy(client, opportunity["id"])

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/purchase",
        json={
            "amount": "2250.00",
            "currency": "EUR",
            "purchased_at": "2099-01-01T00:00:00Z",
            "reason": "Acheté.",
        },
    )
    assert response.status_code == 422


async def test_the_purchase_is_traceable_in_the_history(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity = await _opportunity(client, default_portfolio_id, "ACH-009")
    await _intend_to_buy(client, opportunity["id"])
    await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/purchase",
        json={
            "amount": "2250.00",
            "currency": "EUR",
            "reason": "Négocié à 2 250 € sur place.",
        },
    )

    events = (
        await client.get(f"/api/v1/opportunities/{opportunity['id']}/events")
    ).json()
    reasons = [event["reason"] for event in events["items"]]
    assert "Négocié à 2 250 € sur place." in reasons


async def test_purchased_cannot_be_reached_by_a_status_change(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Sinon le portefeuille se dirait détenteur d'une montre dont aucune ligne
    d'achat n'existe, et dont la trésorerie n'a jamais bougé."""

    opportunity = await _opportunity(client, default_portfolio_id, "ACH-010")
    await _intend_to_buy(client, opportunity["id"])

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/status",
        json={"status": "purchased", "reason": "Tentative de raccourci."},
    )
    assert response.status_code == 422


async def test_an_opportunity_of_another_portfolio_is_not_found(
    client: AsyncClient,
) -> None:
    response = await client.post(
        f"/api/v1/opportunities/{uuid.uuid4()}/purchase",
        json={"amount": "10.00", "currency": "EUR", "reason": "Acheté."},
    )
    assert response.status_code == 404
