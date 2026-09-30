"""Recalcul automatique de la cote et de l'analyse (workflow-and-states.md).

Ajouter, importer, corriger ou exclure un comparable doit faire suivre le
verdict sans que l'utilisateur presse deux boutons dans l'ordre.

Ce que ces tests défendent :

- **le déclenchement** : ni trop tôt (un seul comparable ne fait pas de cote),
  ni pour rien (un fichier entièrement rejeté ne recalcule rien) ;
- **l'immutabilité** : chaque recalcul ajoute une version chaînée, il n'en
  écrase aucune (règle 4) ;
- **l'isolement** : un recalcul qui échoue ne fait jamais perdre le comparable
  qui l'a déclenché.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


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


async def _opportunity(
    client: AsyncClient, portfolio_id: uuid.UUID, ref: str
) -> dict[str, object]:
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
            "price": {"amount": "2400.00", "currency": "EUR"},
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
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


def _payload(amount: str, seller: str) -> dict[str, object]:
    return {
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
    }


async def _add(
    client: AsyncClient, opportunity_id: str, amount: str, seller: str
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/comparables",
        json=_payload(amount, seller),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _count(db_session: AsyncSession, table: str, opportunity_id: str) -> int:
    # `table` vient de ce fichier, jamais d'une entrée extérieure.
    return (
        await db_session.execute(
            text(f"select count(*) from {table} where opportunity_id = :id"),  # noqa: S608
            {"id": opportunity_id},
        )
    ).scalar_one()


# --- Déclenchement -------------------------------------------------------


async def test_a_single_comparable_makes_no_quote_and_says_so(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Un comparable ne fait pas de cote. Le dire vaut mieux que fabriquer un
    chiffre — et ce n'est pas une erreur : la saisie est enregistrée."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "REC-001")

    comparable = await _add(client, opportunity["id"], "3500.00", "s0")

    assert comparable["recalculation"]["status"] == "skipped"
    assert comparable["recalculation"]["reason"] == "insufficient_comparables"
    assert comparable["recalculation"]["valuation_id"] is None
    assert await _count(db_session, "market_valuations", opportunity["id"]) == 0
    assert await _count(db_session, "analyses", opportunity["id"]) == 0


async def test_the_second_comparable_produces_a_quote_and_a_verdict(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """C'est le cas que l'utilisateur attend : deux saisies, un verdict, sans
    presser le moindre bouton."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "REC-002")

    await _add(client, opportunity["id"], "3500.00", "s0")
    second = await _add(client, opportunity["id"], "3600.00", "s1")

    recalculation = second["recalculation"]
    assert recalculation["status"] == "recalculated"
    assert recalculation["valuation_id"] is not None
    assert recalculation["analysis_id"] is not None

    latest = await client.get(
        f"/api/v1/opportunities/{opportunity['id']}/analyses/latest"
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == recalculation["analysis_id"]

    # Le déclencheur est tracé : on doit pouvoir distinguer une analyse
    # demandée d'une analyse déclenchée par les données.
    trigger = (
        await db_session.execute(
            text("select trigger_type from analyses where id = :id"),
            {"id": recalculation["analysis_id"]},
        )
    ).scalar_one()
    assert trigger == "comparable_changed"


async def test_a_manual_analysis_keeps_its_own_trigger(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Ajouter le déclencheur automatique ne doit pas rebaptiser la demande
    explicite de l'utilisateur."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "REC-003")
    await _add(client, opportunity["id"], "3500.00", "s0")
    await _add(client, opportunity["id"], "3600.00", "s1")

    manual = await client.post(f"/api/v1/opportunities/{opportunity['id']}/analyses")
    assert manual.status_code == 201

    trigger = (
        await db_session.execute(
            text("select trigger_type from analyses where id = :id"),
            {"id": manual.json()["id"]},
        )
    ).scalar_one()
    assert trigger == "manual"


# --- Immutabilité --------------------------------------------------------


async def test_each_recalculation_chains_a_new_version(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Règle 4 : rien n'est écrasé. Le troisième comparable ajoute une cote et
    une analyse, chaînée à la précédente."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "REC-004")

    await _add(client, opportunity["id"], "3500.00", "s0")
    second = await _add(client, opportunity["id"], "3600.00", "s1")
    third = await _add(client, opportunity["id"], "3550.00", "s2")

    first_analysis = second["recalculation"]["analysis_id"]
    second_analysis = third["recalculation"]["analysis_id"]
    assert first_analysis != second_analysis

    # Les deux versions existent : la première n'a pas été remplacée.
    assert await _count(db_session, "analyses", opportunity["id"]) == 2
    assert await _count(db_session, "market_valuations", opportunity["id"]) == 2

    previous = (
        await db_session.execute(
            text("select previous_analysis_id from analyses where id = :id"),
            {"id": second_analysis},
        )
    ).scalar_one()
    assert str(previous) == first_analysis


# --- Correction et exclusion --------------------------------------------


async def test_excluding_a_comparable_recalculates_when_told_which_opportunity(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "REC-005")
    first = await _add(client, opportunity["id"], "3500.00", "s0")
    await _add(client, opportunity["id"], "3600.00", "s1")
    await _add(client, opportunity["id"], "3550.00", "s2")
    before = await _count(db_session, "analyses", opportunity["id"])

    response = await client.post(
        f"/api/v1/comparables/{first['id']}/overrides",
        params={"opportunity_id": opportunity["id"]},
        json={
            "excluded": True,
            "exclusion_reason": "Boîtier poli, non comparable.",
            "reason": "Écarté après examen des photos de l'annonce.",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["recalculation"]["status"] == "recalculated"
    assert await _count(db_session, "analyses", opportunity["id"]) == before + 1


async def test_an_override_without_an_opportunity_recalculates_nothing(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Un comparable appartient à une référence, pas à une opportunité. Sans
    savoir laquelle recalculer, on n'en recalcule aucune plutôt que de choisir
    à la place de l'utilisateur."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "REC-006")
    first = await _add(client, opportunity["id"], "3500.00", "s0")
    await _add(client, opportunity["id"], "3600.00", "s1")
    before = await _count(db_session, "analyses", opportunity["id"])

    response = await client.post(
        f"/api/v1/comparables/{first['id']}/overrides",
        json={
            "excluded": True,
            "exclusion_reason": "Boîtier poli, non comparable.",
            "reason": "Écarté après examen des photos de l'annonce.",
        },
    )

    assert response.status_code == 201
    assert response.json()["recalculation"] is None
    assert await _count(db_session, "analyses", opportunity["id"]) == before


# --- Import CSV ----------------------------------------------------------

_CSV_HEADER = (
    "source_name,price_kind,amount,currency,market_status,observed_at,"
    "source_reliability,mechanical_condition,cosmetic_condition,box,papers,"
    "seller_fingerprint"
)


def _row(amount: str, seller: str) -> str:
    observed = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    return (
        f"Chrono24,asking,{amount},EUR,active,{observed},a,verified,excellent,"
        f"true,true,{seller}"
    )


async def test_a_csv_import_recalculates_once_for_the_whole_file(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Un recalcul par ligne publierait cinq versions d'analyse pour un seul
    geste de l'utilisateur."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "REC-007")
    content = "\n".join(
        [_CSV_HEADER]
        + [
            _row(amount, f"s{index}")
            for index, amount in enumerate(
                ["3500.00", "3550.00", "3600.00", "3620.00", "3680.00"]
            )
        ]
    )

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/comparables/import",
        json={"content": content},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["imported"] == 5
    assert body["recalculation"]["status"] == "recalculated"
    assert await _count(db_session, "analyses", opportunity["id"]) == 1
    assert await _count(db_session, "market_valuations", opportunity["id"]) == 1


async def test_an_import_that_adds_nothing_recalculates_nothing(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "REC-008")
    content = "\n".join([_CSV_HEADER, "Chrono24,asking,pas-un-montant,EUR"])

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/comparables/import",
        json={"content": content},
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 0
    assert response.json()["recalculation"] is None
    assert await _count(db_session, "analyses", opportunity["id"]) == 0


# --- Isolement -----------------------------------------------------------


async def test_a_portfolio_without_cash_still_gets_its_quote(
    client: AsyncClient, db_session: AsyncSession, default_portfolio_id: uuid.UUID
) -> None:
    """Sans trésorerie l'analyse est refusée (422 en mode manuel). En mode
    automatique on garde ce qui a pu être calculé — la cote — et on dit
    pourquoi le reste manque."""

    opportunity = await _opportunity(client, default_portfolio_id, "REC-009")
    await _add(client, opportunity["id"], "3500.00", "s0")
    second = await _add(client, opportunity["id"], "3600.00", "s1")

    recalculation = second["recalculation"]
    assert recalculation["status"] == "valuation_only"
    assert recalculation["valuation_id"] is not None
    assert recalculation["analysis_id"] is None
    assert recalculation["detail"]  # la raison est dite, pas seulement un code
    assert await _count(db_session, "market_valuations", opportunity["id"]) == 1
    assert await _count(db_session, "analyses", opportunity["id"]) == 0


async def test_a_failing_recalculation_never_loses_the_comparable(
    client: AsyncClient,
    db_session: AsyncSession,
    default_portfolio_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le comparable est enregistré avant le recalcul. Une panne inattendue du
    moteur ne doit ni renvoyer une erreur 500, ni faire disparaître la saisie."""

    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "REC-010")
    await _add(client, opportunity["id"], "3500.00", "s0")

    async def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError("panne simulée du moteur")

    monkeypatch.setattr("app.scoring.application.recalculate.compute_valuation", broken)

    second = await _add(client, opportunity["id"], "3600.00", "s1")

    assert second["recalculation"]["status"] == "failed"
    assert second["recalculation"]["reason"] == "unexpected_error"
    # Rien de la panne ne fuit vers le client.
    assert "panne simulée" not in str(second["recalculation"])

    listed = await client.get(f"/api/v1/opportunities/{opportunity['id']}/comparables")
    assert len(listed.json()["items"]) == 2


async def test_a_failing_analysis_keeps_the_fresh_quote(
    client: AsyncClient,
    db_session: AsyncSession,
    default_portfolio_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _fund(db_session, default_portfolio_id, "20000.00")
    opportunity = await _opportunity(client, default_portfolio_id, "REC-011")
    await _add(client, opportunity["id"], "3500.00", "s0")

    async def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError("panne simulée de l'analyse")

    monkeypatch.setattr("app.scoring.application.recalculate.run_analysis", broken)

    second = await _add(client, opportunity["id"], "3600.00", "s1")

    assert second["recalculation"]["status"] == "valuation_only"
    assert second["recalculation"]["valuation_id"] is not None
    assert "panne simulée" not in str(second["recalculation"])
    assert await _count(db_session, "market_valuations", opportunity["id"]) == 1
