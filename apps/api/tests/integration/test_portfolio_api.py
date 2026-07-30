from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _movement(
    client: AsyncClient,
    portfolio_id: uuid.UUID,
    kind: str,
    amount: str,
    **extra: object,
):
    return await client.post(
        f"/api/v1/portfolios/{portfolio_id}/ledger-entries",
        json={"kind": kind, "amount": amount, "currency": "EUR", **extra},
    )


async def _overview(client: AsyncClient, portfolio_id: uuid.UUID) -> dict:
    response = await client.get(f"/api/v1/portfolios/{portfolio_id}/overview")
    assert response.status_code == 200, response.text
    return response.json()


# --- Trésorerie ----------------------------------------------------------


async def test_an_empty_portfolio_has_no_cash(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    body = await _overview(client, default_portfolio_id)
    assert body["available_cash_eur"] == "0.00"
    assert body["holdings"] == []
    assert body["movements"] == []


async def test_the_real_opening_position(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Capital de départ 3 859,20 €, trois montres payées 950, 750 et 1 112 € :
    il doit rester 1 047,20 € de trésorerie."""

    assert (
        await _movement(client, default_portfolio_id, "capital_contribution", "3859.20")
    ).status_code == 201

    for paid in ("950.00", "750.00", "1112.00"):
        assert (
            await _movement(client, default_portfolio_id, "negative_adjustment", paid)
        ).status_code == 201

    body = await _overview(client, default_portfolio_id)
    assert body["available_cash_eur"] == "1047.20"


async def test_adding_capital_mid_course(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """L'apport en cours de route doit débloquer la capacité d'achat sans
    qu'on retouche l'historique."""

    await _movement(client, default_portfolio_id, "capital_contribution", "1000.00")
    before = (await _overview(client, default_portfolio_id))["available_cash_eur"]

    await _movement(client, default_portfolio_id, "capital_contribution", "2500.00")
    after = await _overview(client, default_portfolio_id)

    assert before == "1000.00"
    assert after["available_cash_eur"] == "3500.00"
    # L'historique est intact : deux écritures, pas une corrigée.
    assert len(after["movements"]) == 2


async def test_a_withdrawal_reduces_the_cash(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    await _movement(client, default_portfolio_id, "capital_contribution", "1000.00")
    await _movement(client, default_portfolio_id, "withdrawal", "300.00")

    body = await _overview(client, default_portfolio_id)
    assert body["available_cash_eur"] == "700.00"


# --- Garde-fous ----------------------------------------------------------


async def test_a_withdrawal_beyond_the_cash_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Un découvert se constate quand il arrive ; il ne se saisit pas."""

    await _movement(client, default_portfolio_id, "capital_contribution", "500.00")
    response = await _movement(client, default_portfolio_id, "withdrawal", "800.00")

    assert response.status_code == 422
    assert response.json()["error"]["details"]["available_cash_eur"] == "500.00"


async def test_kinds_with_a_counterpart_elsewhere_are_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Un paiement d'achat a sa ligne dans `purchases` : le saisir ici ferait
    diverger le registre des opérations qu'il reflète."""

    response = await _movement(
        client, default_portfolio_id, "purchase_payment", "950.00"
    )
    assert response.status_code == 422


async def test_the_sign_belongs_to_the_kind(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    response = await _movement(
        client, default_portfolio_id, "capital_contribution", "-500.00"
    )
    assert response.status_code == 422


async def test_a_future_movement_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Un mouvement futur fausserait une trésorerie présentée comme
    disponible aujourd'hui."""

    later = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    response = await _movement(
        client,
        default_portfolio_id,
        "capital_contribution",
        "500.00",
        occurred_at=later,
    )
    assert response.status_code == 422


async def test_an_unknown_portfolio_is_not_found(client: AsyncClient) -> None:
    """404 et non 403 : l'existence d'un portefeuille étranger ne doit pas
    transparaître dans le code de statut."""

    assert (
        await _movement(client, uuid.uuid4(), "capital_contribution", "10.00")
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/portfolios/{uuid.uuid4()}/overview")
    ).status_code == 404


async def test_amounts_travel_as_decimal_strings(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    created = await _movement(
        client, default_portfolio_id, "capital_contribution", "1234.56"
    )
    body = created.json()
    for field in ("amount_source", "amount_eur", "rate_to_eur"):
        assert isinstance(body[field], str), field
    assert body["amount_eur"] == "1234.56"


async def test_the_conversion_trace_is_kept(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Règle 3 : devise source, montant EUR, taux, source et horodatage."""

    body = (
        await _movement(client, default_portfolio_id, "capital_contribution", "100.00")
    ).json()
    assert body["currency"] == "EUR"
    assert body["rate_to_eur"] == "1.000000000000"
    assert body["fx_source"]
    assert body["fx_rate_at"]


async def test_an_unavailable_rate_blocks_the_entry(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Aucun taux frais pour le dollar : convertir au petit bonheur
    fausserait la trésorerie sans laisser de trace."""

    response = await client.post(
        f"/api/v1/portfolios/{default_portfolio_id}/ledger-entries",
        json={"kind": "capital_contribution", "amount": "100.00", "currency": "USD"},
    )
    # 503 et non 422 : l'absence de taux frais n'est pas une faute de
    # l'appelant, c'est une dépendance indisponible (catalogue d'erreurs).
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "FX_RATE_UNAVAILABLE"


# --- Immuabilité et stock ------------------------------------------------


async def test_a_ledger_entry_cannot_be_modified(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Le registre est append-only : on ne corrige pas une écriture, on en
    passe une autre en sens inverse."""

    body = (
        await _movement(client, default_portfolio_id, "capital_contribution", "100.00")
    ).json()

    with pytest.raises(Exception) as excinfo:
        await db_session.execute(
            text("update portfolio_ledger_entries set amount_eur = 999 where id = :id"),
            {"id": body["id"]},
        )
        await db_session.commit()
    assert "IMMUTABLE_RESOURCE" in str(excinfo.value)
    await db_session.rollback()


async def test_the_stock_is_detailed_watch_by_watch(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Annoncer un taux d'immobilisation sans dire quelles montres immobilisent
    le capital ne dit pas quoi vendre."""

    opportunity = (
        await client.post(
            "/api/v1/opportunities",
            json={
                "portfolio_id": str(default_portfolio_id),
                "source": {"mode": "manual", "manual_identifier": "PF-001"},
                "watch": {
                    "brand": "Longines",
                    "reference": "L2.257.4.57.6",
                    "mechanical_condition": "verified",
                    "cosmetic_condition": "excellent",
                    "box": True,
                    "papers": True,
                },
                "seller": {"country_code": "FR", "seller_type": "private"},
                "price": {"amount": "950.00", "currency": "EUR"},
            },
        )
    ).json()

    await db_session.execute(
        text(
            """
            insert into purchases (portfolio_id, opportunity_id, amount_source,
              currency, amount_eur, rate_to_eur, fx_rate_at, fx_source,
              purchased_at, created_by_user_id)
            select :pf, :opp, 950, 'EUR', 950, 1, now(), 'saisie manuelle',
                   now(), id from users limit 1
            """
        ),
        {"pf": default_portfolio_id, "opp": opportunity["id"]},
    )
    await db_session.commit()

    body = await _overview(client, default_portfolio_id)
    assert body["stock_at_cost_eur"] == "950.00"
    assert len(body["holdings"]) == 1
    assert body["holdings"][0]["brand"] == "Longines"
    assert body["holdings"][0]["cost_eur"] == "950.00"


async def test_the_total_capital_is_cash_plus_stock_at_cost(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    await _movement(client, default_portfolio_id, "capital_contribution", "2000.00")
    body = await _overview(client, default_portfolio_id)
    assert body["total_capital_eur"] == "2000.00"


# --- Stratégie -----------------------------------------------------------


async def test_the_default_strategy_has_no_resale_platform(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Aucune plateforme de revente supposée : où l'on revend est une décision
    qu'on n'a pas encore prise."""

    response = await client.get(f"/api/v1/portfolios/{default_portfolio_id}/strategy")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 1
    assert body["resale_platform_code"] is None
    assert body["minimum_roi"] == "0.1000000000"


async def test_setting_the_resale_platform_opens_a_new_version(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Une version n'est jamais réécrite : une analyse figée référence celle
    qui l'a produite."""

    first = (
        await client.get(f"/api/v1/portfolios/{default_portfolio_id}/strategy")
    ).json()

    created = await client.post(
        f"/api/v1/portfolios/{default_portfolio_id}/strategy",
        json={"resale_platform_code": "chrono24"},
    )
    assert created.status_code == 201, created.text
    body = created.json()

    assert body["version"] == first["version"] + 1
    assert body["id"] != first["id"]
    assert body["resale_platform_code"] == "chrono24"


async def test_unmentioned_terms_are_carried_over(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Corriger un paramètre ne doit pas obliger à retaper les autres :
    exiger la saisie complète inviterait à la faute de recopie."""

    before = (
        await client.get(f"/api/v1/portfolios/{default_portfolio_id}/strategy")
    ).json()

    after = (
        await client.post(
            f"/api/v1/portfolios/{default_portfolio_id}/strategy",
            json={"minimum_roi": "0.25"},
        )
    ).json()

    assert after["minimum_roi"] == "0.2500000000"
    assert after["minimum_profit_eur"] == before["minimum_profit_eur"]
    assert after["negotiation_buffer"] == before["negotiation_buffer"]


async def test_the_resale_platform_can_be_removed_explicitly(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Un champ vide ne saurait exprimer « retire-la » sans ambiguïté : il se
    confondrait avec « n'y touche pas »."""

    await client.post(
        f"/api/v1/portfolios/{default_portfolio_id}/strategy",
        json={"resale_platform_code": "catawiki"},
    )
    cleared = (
        await client.post(
            f"/api/v1/portfolios/{default_portfolio_id}/strategy",
            json={"clear_resale_platform": True},
        )
    ).json()
    assert cleared["resale_platform_code"] is None


async def test_an_unknown_resale_platform_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    response = await client.post(
        f"/api/v1/portfolios/{default_portfolio_id}/strategy",
        json={"resale_platform_code": "brocante-du-coin"},
    )
    assert response.status_code == 404


async def test_a_strategy_version_cannot_be_modified(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    body = (
        await client.get(f"/api/v1/portfolios/{default_portfolio_id}/strategy")
    ).json()

    with pytest.raises(Exception) as excinfo:
        await db_session.execute(
            text("update strategy_versions set minimum_roi = 0.9 where id = :id"),
            {"id": body["id"]},
        )
        await db_session.commit()
    assert "IMMUTABLE_RESOURCE" in str(excinfo.value)
    await db_session.rollback()
