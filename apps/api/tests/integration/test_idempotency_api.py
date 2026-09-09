"""Ce que l'en-tête `Idempotency-Key` protège, et ce qu'il ne protège pas.

Chaque test part du double envoi réel — deux requêtes identiques, l'une après
l'autre ou en même temps — plutôt que d'un appel direct au registre. C'est la
seule façon de vérifier ce qui compte : le nombre d'écritures financières
laissées derrière.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.db.models.enums import LedgerEntryKind
from app.shared.infrastructure.db.models.operations import Purchase
from app.shared.infrastructure.db.models.portfolio_ledger import PortfolioLedgerEntry

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


async def _opportunity(client: AsyncClient, portfolio_id: uuid.UUID, ref: str) -> str:
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
    return str(created.json()["id"])


async def _intend_to_buy(client: AsyncClient, opportunity_id: str) -> None:
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/status",
        json={"status": "buy", "reason": "Affaire retenue après analyse."},
    )
    assert response.status_code == 200, response.text


async def _count(db_session: AsyncSession, model: type, portfolio_id: uuid.UUID) -> int:
    return int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(model)
                .where(model.portfolio_id == portfolio_id)
            )
        ).scalar_one()
    )


_MOVEMENT = {
    "kind": "capital_contribution",
    "amount": "1000.00",
    "currency": "EUR",
    "occurred_at": "2026-03-01T10:00:00Z",
    "notes": "Apport de mars.",
}


async def test_a_movement_sent_twice_without_a_key_is_recorded_twice(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Le double envoi n'est pas une crainte théorique : sans clé, il passe.

    Le registre de trésorerie est append-only et sans contrainte d'unicité —
    deux apports identiques du même jour sont un cas légitime. Rien dans la
    base ne peut donc distinguer le doublon accidentel du doublon voulu :
    c'est l'appelant qui doit le dire, et l'en-tête est le seul endroit où il
    peut le faire.
    """

    url = f"/api/v1/portfolios/{default_portfolio_id}/ledger-entries"
    first = await client.post(url, json=_MOVEMENT)
    second = await client.post(url, json=_MOVEMENT)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] != second.json()["id"]
    assert await _count(db_session, PortfolioLedgerEntry, default_portfolio_id) == 2


async def test_the_same_key_replays_the_first_answer_without_writing_again(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    url = f"/api/v1/portfolios/{default_portfolio_id}/ledger-entries"
    headers = {"Idempotency-Key": "apport-mars-2026"}

    first = await client.post(url, json=_MOVEMENT, headers=headers)
    second = await client.post(url, json=_MOVEMENT, headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    # Le rejeu rend la réponse d'origine, identifiant compris : l'appelant ne
    # peut pas distinguer les deux, et c'est exactement ce qu'on veut.
    assert second.json() == first.json()
    assert await _count(db_session, PortfolioLedgerEntry, default_portfolio_id) == 1


async def test_two_simultaneous_requests_write_once(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Le cas que le contrôle « lire puis insérer » laisserait passer.

    Les deux requêtes partent ensemble : aucune ne peut voir la réservation de
    l'autre par une lecture préalable, puisqu'au moment où elles lisent, ni
    l'une ni l'autre n'a encore écrit. Seul l'index unique tranche.
    """

    url = f"/api/v1/portfolios/{default_portfolio_id}/ledger-entries"
    headers = {"Idempotency-Key": "apport-simultane"}

    first, second = await asyncio.gather(
        client.post(url, json=_MOVEMENT, headers=headers),
        client.post(url, json=_MOVEMENT, headers=headers),
    )

    statuses = sorted([first.status_code, second.status_code])
    # La perdante est refusée (409) si la gagnante n'a pas encore répondu, ou
    # rejouée (201) si elle a fini entre-temps. Les deux issues sont correctes ;
    # ce qui ne l'est pas, ce sont deux écritures.
    assert statuses in ([201, 201], [201, 409]), (first.text, second.text)
    assert await _count(db_session, PortfolioLedgerEntry, default_portfolio_id) == 1

    refused = [r for r in (first, second) if r.status_code == 409]
    for response in refused:
        assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        assert response.json()["error"]["details"]["reason"] == "in_progress"


async def test_the_same_key_with_a_different_body_is_refused(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Réemployer une clé pour autre chose est une erreur, pas un rejeu.

    Rendre silencieusement la première réponse serait pire que le doublon :
    l'appelant croirait son second mouvement enregistré alors que rien ne
    l'aurait été.
    """

    url = f"/api/v1/portfolios/{default_portfolio_id}/ledger-entries"
    headers = {"Idempotency-Key": "cle-reemployee"}

    first = await client.post(url, json=_MOVEMENT, headers=headers)
    assert first.status_code == 201, first.text

    second = await client.post(
        url, json={**_MOVEMENT, "amount": "2000.00"}, headers=headers
    )

    assert second.status_code == 409, second.text
    error = second.json()["error"]
    assert error["code"] == "IDEMPOTENCY_CONFLICT"
    assert error["details"]["reason"] == "payload_mismatch"
    assert await _count(db_session, PortfolioLedgerEntry, default_portfolio_id) == 1


async def test_a_purchase_sent_twice_leaves_one_operation_and_one_entry(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """L'achat écrit dans deux tables d'un seul geste. Les deux doivent
    compter une ligne, pas seulement celle qui porte l'opération."""

    await _fund(db_session, default_portfolio_id)
    opportunity_id = await _opportunity(client, default_portfolio_id, "IDEM-ACH")
    await _intend_to_buy(client, opportunity_id)

    url = f"/api/v1/opportunities/{opportunity_id}/purchase"
    body = {
        "amount": "2250.00",
        "currency": "EUR",
        "reason": "Négocié à 2 250 € sur place.",
    }
    headers = {"Idempotency-Key": "achat-tudor-79030n"}

    first = await client.post(url, json=body, headers=headers)
    second = await client.post(url, json=body, headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json() == first.json()

    assert await _count(db_session, Purchase, default_portfolio_id) == 1
    payments = (
        await db_session.execute(
            select(func.count())
            .select_from(PortfolioLedgerEntry)
            .where(
                PortfolioLedgerEntry.portfolio_id == default_portfolio_id,
                PortfolioLedgerEntry.kind == LedgerEntryKind.PURCHASE_PAYMENT,
            )
        )
    ).scalar_one()
    assert payments == 1


async def test_a_key_burnt_by_a_refusal_can_be_used_again(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Un échec ne consomme pas la clé.

    L'achat est d'abord refusé parce que l'opportunité n'est pas au statut
    `buy`. Rien n'a été écrit : la même clé doit encore servir une fois la
    situation corrigée, sinon une panne passagère condamnerait l'opération
    pour vingt-quatre heures.
    """

    await _fund(db_session, default_portfolio_id)
    opportunity_id = await _opportunity(client, default_portfolio_id, "IDEM-REPRISE")

    url = f"/api/v1/opportunities/{opportunity_id}/purchase"
    body = {"amount": "2250.00", "currency": "EUR", "reason": "Achat sur place."}
    headers = {"Idempotency-Key": "achat-a-reprendre"}

    refused = await client.post(url, json=body, headers=headers)
    assert refused.status_code >= 400, refused.text
    assert await _count(db_session, Purchase, default_portfolio_id) == 0

    await _intend_to_buy(client, opportunity_id)
    accepted = await client.post(url, json=body, headers=headers)

    assert accepted.status_code == 201, accepted.text
    assert await _count(db_session, Purchase, default_portfolio_id) == 1


async def test_a_key_that_is_too_long_is_rejected_before_any_effect(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    url = f"/api/v1/portfolios/{default_portfolio_id}/ledger-entries"
    response = await client.post(
        url, json=_MOVEMENT, headers={"Idempotency-Key": "x" * 129}
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert await _count(db_session, PortfolioLedgerEntry, default_portfolio_id) == 0
