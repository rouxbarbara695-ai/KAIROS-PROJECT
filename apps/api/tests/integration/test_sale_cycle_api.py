from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


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


async def _status(client: AsyncClient, oid: str, target: str) -> int:
    response = await client.post(
        f"/api/v1/opportunities/{oid}/status",
        json={"status": target, "reason": f"Passage à {target}."},
    )
    return response.status_code


async def _in_stock(client: AsyncClient, portfolio_id: uuid.UUID, ref: str) -> str:
    """Amène une opportunité jusqu'au stock : créée, décidée, achetée, reçue."""

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
    oid: str = created.json()["id"]

    assert await _status(client, oid, "buy") == 200
    bought = await client.post(
        f"/api/v1/opportunities/{oid}/purchase",
        json={"amount": "2250.00", "currency": "EUR", "reason": "Négocié."},
    )
    assert bought.status_code == 201, bought.text
    assert await _status(client, oid, "in_stock") == 200
    return oid


async def _overview(client: AsyncClient, portfolio_id: uuid.UUID) -> dict:
    body: dict = (
        await client.get(f"/api/v1/portfolios/{portfolio_id}/overview")
    ).json()
    return body


async def test_the_whole_cycle_runs_and_the_cash_comes_back(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Achat à 2 250 €, revente encaissée à 3 200 € : la trésorerie doit
    revenir au-dessus de son point de départ, et le stock se vider."""

    await _fund(db_session, default_portfolio_id)
    start = await _overview(client, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-001")

    listed = await client.post(
        f"/api/v1/opportunities/{oid}/sale-listing",
        json={
            "asking_amount": "3400.00",
            "currency": "EUR",
            "platform_code": "chrono24",
            "reason": "Mise en vente au-dessus de la cote pour négocier.",
        },
    )
    assert listed.status_code == 201, listed.text

    assert await _status(client, oid, "awaiting_buyer_payment") == 200

    sold = await client.post(
        f"/api/v1/opportunities/{oid}/sale",
        json={
            "realized_amount": "3400.00",
            "currency": "EUR",
            "reason": "Vendue au prix demandé.",
        },
    )
    assert sold.status_code == 201, sold.text

    # Les fonds sont retenus : la trésorerie ne doit pas encore avoir bougé.
    held = await _overview(client, default_portfolio_id)
    assert Decimal(held["available_cash_eur"]) == Decimal(
        start["available_cash_eur"]
    ) - Decimal("2250.00")

    paid = await client.post(
        f"/api/v1/opportunities/{oid}/payout",
        json={
            "amount": "3200.00",
            "currency": "EUR",
            "reason": "Virement reçu, commission déduite.",
        },
    )
    assert paid.status_code == 200, paid.text

    end = await _overview(client, default_portfolio_id)
    assert Decimal(end["available_cash_eur"]) == Decimal(
        start["available_cash_eur"]
    ) + Decimal("950.00")
    assert Decimal(end["stock_at_cost_eur"]) == Decimal(start["stock_at_cost_eur"])
    assert (await client.get(f"/api/v1/opportunities/{oid}")).json()["status"] == "sold"


async def test_a_sale_does_not_move_the_cash(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """La plateforme retient les fonds jusqu'à la livraison. Les compter à la
    vente ferait apparaître un argent dont on ne dispose pas — et le pilier
    portefeuille se tromperait dans le sens qui autorise un achat de plus."""

    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-002")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale-listing",
        json={"asking_amount": "3400.00", "currency": "EUR", "reason": "En vente."},
    )
    await _status(client, oid, "awaiting_buyer_payment")

    before = await _overview(client, default_portfolio_id)
    await client.post(
        f"/api/v1/opportunities/{oid}/sale",
        json={"realized_amount": "3400.00", "currency": "EUR", "reason": "Vendue."},
    )
    after = await _overview(client, default_portfolio_id)

    assert after["available_cash_eur"] == before["available_cash_eur"]

    kinds = set(
        (
            await db_session.execute(
                text(
                    "select kind from portfolio_ledger_entries "
                    "where opportunity_id = :id"
                ),
                {"id": oid},
            )
        ).scalars()
    )
    assert kinds == {"purchase_payment"}


async def test_what_lands_on_the_account_is_what_counts(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Le prix réalisé est 3 400 €, l'encaissement 3 200 € : c'est le second
    qui entre en trésorerie. Compter le premier ferait croire à 200 € qu'on n'a
    jamais reçus."""

    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-003")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale-listing",
        json={"asking_amount": "3400.00", "currency": "EUR", "reason": "En vente."},
    )
    await _status(client, oid, "awaiting_buyer_payment")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale",
        json={"realized_amount": "3400.00", "currency": "EUR", "reason": "Vendue."},
    )

    before = await _overview(client, default_portfolio_id)
    await client.post(
        f"/api/v1/opportunities/{oid}/payout",
        json={"amount": "3200.00", "currency": "EUR", "reason": "Virement reçu."},
    )
    after = await _overview(client, default_portfolio_id)

    received = Decimal(after["available_cash_eur"]) - Decimal(
        before["available_cash_eur"]
    )
    assert received == Decimal("3200.00")


async def test_an_unstated_payout_falls_back_to_the_realized_price(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Une vente sans intermédiaire : ce qui est convenu est ce qui arrive."""

    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-004")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale-listing",
        json={"asking_amount": "3400.00", "currency": "EUR", "reason": "En vente."},
    )
    await _status(client, oid, "awaiting_buyer_payment")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale",
        json={"realized_amount": "3400.00", "currency": "EUR", "reason": "Vendue."},
    )

    before = await _overview(client, default_portfolio_id)
    response = await client.post(
        f"/api/v1/opportunities/{oid}/payout",
        json={"reason": "Remis en main propre, espèces."},
    )
    assert response.status_code == 200, response.text
    after = await _overview(client, default_portfolio_id)

    received = Decimal(after["available_cash_eur"]) - Decimal(
        before["available_cash_eur"]
    )
    assert received == Decimal("3400.00")


async def test_listing_closes_when_the_sale_is_recorded(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-005")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale-listing",
        json={"asking_amount": "3400.00", "currency": "EUR", "reason": "En vente."},
    )
    await _status(client, oid, "awaiting_buyer_payment")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale",
        json={"realized_amount": "3400.00", "currency": "EUR", "reason": "Vendue."},
    )

    row = (
        await db_session.execute(
            text(
                "select status, ended_at from sale_listings where opportunity_id = :id"
            ),
            {"id": oid},
        )
    ).one()
    assert row.status == "sold"
    assert row.ended_at is not None


async def test_selling_is_refused_before_the_watch_is_listed(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-006")

    response = await client.post(
        f"/api/v1/opportunities/{oid}/sale",
        json={"realized_amount": "3400.00", "currency": "EUR", "reason": "Vendue."},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"


async def test_listing_for_sale_cannot_be_reached_by_a_status_change(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Sinon la montre serait « en vente » sans qu'aucune annonce n'existe, ni
    aucun prix demandé."""

    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-007")

    assert await _status(client, oid, "listed_for_sale") == 422


async def test_a_buyer_who_backs_out_returns_the_watch_to_sale(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Ce retour ne crée aucune annonce : elle existe déjà. Interdire le statut
    plutôt que la transition bloquerait ce cas légitime."""

    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-008")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale-listing",
        json={"asking_amount": "3400.00", "currency": "EUR", "reason": "En vente."},
    )
    await _status(client, oid, "awaiting_buyer_payment")

    assert await _status(client, oid, "listed_for_sale") == 200


async def test_an_unknown_resale_platform_is_refused(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-009")

    response = await client.post(
        f"/api/v1/opportunities/{oid}/sale-listing",
        json={
            "asking_amount": "3400.00",
            "currency": "EUR",
            "platform_code": "brocante-du-coin",
            "reason": "En vente.",
        },
    )
    assert response.status_code == 404


async def test_a_payout_cannot_precede_its_sale(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-010")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale-listing",
        json={"asking_amount": "3400.00", "currency": "EUR", "reason": "En vente."},
    )
    await _status(client, oid, "awaiting_buyer_payment")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale",
        json={"realized_amount": "3400.00", "currency": "EUR", "reason": "Vendue."},
    )

    response = await client.post(
        f"/api/v1/opportunities/{oid}/payout",
        json={"received_at": "2020-01-01T00:00:00Z", "reason": "Virement."},
    )
    assert response.status_code == 422


async def test_a_sold_watch_is_terminal(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Une vente ne se défait pas : on la corrige par une écriture inverse."""

    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-011")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale-listing",
        json={"asking_amount": "3400.00", "currency": "EUR", "reason": "En vente."},
    )
    await _status(client, oid, "awaiting_buyer_payment")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale",
        json={"realized_amount": "3400.00", "currency": "EUR", "reason": "Vendue."},
    )
    await client.post(
        f"/api/v1/opportunities/{oid}/payout",
        json={"reason": "Virement reçu."},
    )

    assert await _status(client, oid, "in_stock") == 409
    second = await client.post(
        f"/api/v1/opportunities/{oid}/payout",
        json={"reason": "Deuxième encaissement ?"},
    )
    assert second.status_code == 409


async def test_the_cycle_is_traceable_end_to_end(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Chaque étape laisse sa trace : c'est ce qui permet d'expliquer, six mois
    après, ce que le portefeuille a fait."""

    await _fund(db_session, default_portfolio_id)
    oid = await _in_stock(client, default_portfolio_id, "CYC-012")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale-listing",
        json={"asking_amount": "3400.00", "currency": "EUR", "reason": "En vente."},
    )
    await _status(client, oid, "awaiting_buyer_payment")
    await client.post(
        f"/api/v1/opportunities/{oid}/sale",
        json={"realized_amount": "3400.00", "currency": "EUR", "reason": "Vendue."},
    )
    await client.post(
        f"/api/v1/opportunities/{oid}/payout", json={"reason": "Virement reçu."}
    )

    actions = set(
        (
            await db_session.execute(
                text("select action from audit_events where resource_id = :id"),
                {"id": oid},
            )
        ).scalars()
    )
    assert {
        "purchase_recorded",
        "listed_for_sale",
        "sale_recorded",
        "payout_received",
    } <= actions
