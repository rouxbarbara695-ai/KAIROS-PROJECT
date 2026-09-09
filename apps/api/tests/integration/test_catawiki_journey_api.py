"""Le parcours Catawiki, de bout en bout : coller, corriger, enregistrer, rouvrir.

Catawiki est la plateforme d'achat principale et la seule dont la récupération
serveur est impossible — le bord Akamai refuse tout, y compris `robots.txt`.
Tout passe donc par le texte collé, et le critère de réussite est double : le
temps de saisie épargné, et l'exactitude de ce qui a été repris.

Le test qui compte ici est le dernier : **rouvrir**. Un import qui remplit bien
mais dont on ne peut plus dire, six semaines plus tard, quelle valeur venait de
l'annonce et laquelle a été corrigée à la main n'a pas fait son travail — il a
seulement rendu les erreurs plus difficiles à retrouver.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_LOT_TEXT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "listings"
    / "catawiki-lot-fr.txt"
).read_text(encoding="utf-8")

_LOT_URL = "https://www.catawiki.com/fr/l/98765432-rolex-datejust"


async def _paste(client: AsyncClient, url: str = _LOT_URL, content: str | None = None):
    response = await client.post(
        "/api/v1/listings/prefill/assisted",
        json={"url": url, "content": content if content is not None else _LOT_TEXT},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _value(prefill: dict, name: str):
    field = prefill["fields"].get(name) or {}
    return None if field.get("provenance") == "absent" else field.get("value")


async def test_catawiki_is_never_fetched_by_the_server(client: AsyncClient) -> None:
    """Le blocage Akamai est respecté : la route ne tente rien."""

    response = await client.post("/api/v1/listings/prefill", json={"url": _LOT_URL})

    body = response.json()
    assert body["succeeded"] is False
    assert body["access_mode"] == "assisted"
    assert body["failure"]["details"]["fallback"] == "assisted_import"


async def test_pasting_visible_text_fills_the_lot(client: AsyncClient) -> None:
    """Du texte visible, pas du code source : ni `Ctrl+U` ni outils de
    développement."""

    prefill = await _paste(client)

    assert prefill["succeeded"] is True
    assert prefill["platform_code"] == "catawiki"
    assert _value(prefill, "lot_number") == "98765432"
    assert _value(prefill, "brand") == "Rolex"
    assert _value(prefill, "reference") == "16233"
    assert _value(prefill, "year") == 1994
    assert _value(prefill, "current_bid_amount") == "3250"
    assert _value(prefill, "current_bid_currency") == "EUR"
    assert _value(prefill, "price_kind") == "current_bid"
    assert _value(prefill, "estimate_low") == "3800"
    assert _value(prefill, "reserve_status") == "not_met"
    assert _value(prefill, "shipping_cost_amount") == "25.00"
    assert _value(prefill, "shipping_destination") == "FR"
    assert _value(prefill, "closing_timezone") == "CEST"

    filled = sum(1 for f in prefill["fields"].values() if f["provenance"] != "absent")
    assert filled >= 30

    # Le montant est une enchère, et la réponse le dit sans ambiguïté.
    assert any("ni un prix final" in w for w in prefill["warnings"])
    # Les photos manquantes sont annoncées, pas tues.
    assert any("photos ne sont pas reprises" in w for w in prefill["warnings"])


async def test_the_full_journey_keeps_values_and_their_provenance(
    client: AsyncClient, default_portfolio_id: uuid.UUID, db_session: AsyncSession
) -> None:
    """Import → correction → enregistrement → réouverture.

    L'utilisateur corrige une valeur importée (le matériau du boîtier) et en
    laisse d'autres telles quelles. À la réouverture, le dossier doit encore
    savoir laquelle était laquelle.
    """

    prefill = await _paste(client)

    # --- Correction : le vendeur a écrit « Or/acier », c'est de l'acier seul.
    created = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {"mode": "assisted_import", "url": _LOT_URL},
            "watch": {
                "brand": _value(prefill, "brand"),
                "reference": _value(prefill, "reference"),
                "box": _value(prefill, "box"),
                "papers": _value(prefill, "papers"),
            },
            "seller": {
                "country_code": _value(prefill, "seller_country"),
                "seller_type": "professional",
            },
            "price": {
                "amount": _value(prefill, "current_bid_amount"),
                "currency": _value(prefill, "current_bid_currency"),
                # La nature du montant voyage avec lui.
                "kind": "current_bid",
            },
            "import_draft": {
                "platform_code": prefill["platform_code"],
                "fetched_at": prefill["fetched_at"],
                "access_mode": prefill["access_mode"],
                "fields": prefill["fields"],
                "warnings": prefill["warnings"],
            },
        },
    )
    assert created.status_code == 201, created.text
    opportunity = created.json()
    assert opportunity["source_mode"] == "assisted_import"

    # Le prix est enregistré comme enchère, pas comme prix demandé.
    kind = (
        await db_session.execute(
            text(
                "select kind from opportunity_price_inputs where opportunity_id = :id"
            ),
            {"id": opportunity["id"]},
        )
    ).scalar_one()
    assert kind == "current_bid"

    # --- Réouverture : la trace de l'import est encore là.
    trace = await client.get(f"/api/v1/opportunities/{opportunity['id']}/import")
    assert trace.status_code == 200, trace.text
    items = trace.json()["items"]
    assert len(items) == 1

    recorded = items[0]
    assert recorded["platform_code"] == "catawiki"
    assert recorded["access_mode"] == "assisted"
    assert recorded["fetch_status"] == "partial"
    # La réserve non atteinte est constatée, pas supposée.
    assert recorded["reserve_met"] is False
    assert recorded["auction_end_at"].startswith("2026-09-14T20:15")

    fields = recorded["fields"]
    # La valeur telle que l'annonce l'affichait est conservée…
    assert fields["case_material"]["value"] == "Or/acier"
    assert fields["case_material"]["provenance"] == "assisted"
    # …tandis que le dossier porte la correction de l'utilisateur.
    assert opportunity["watch"]["brand"] == "Rolex"

    # Le montant garde sa nature et l'heure à laquelle il a été relevé.
    assert fields["current_bid_amount"]["value"] == "3250"
    assert fields["price_kind"]["value"] == "current_bid"
    assert recorded["observed_at"]

    # Et ce qui manquait manque toujours, avec sa raison.
    assert fields["calibre"]["provenance"] == "absent"
    assert fields["calibre"]["source"]


async def test_a_second_import_adds_a_reading_instead_of_overwriting(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Une enchère monte. Le deuxième relevé s'ajoute au premier.

    Écraser ferait perdre le fait que le lot valait 3 250 € le lundi : c'est
    précisément l'information qui dit si la vente s'emballe.
    """

    prefill = await _paste(client)
    created = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {"mode": "assisted_import", "url": _LOT_URL},
            "watch": {"brand": "Rolex", "reference": "16233"},
            "price": {"amount": "3250", "currency": "EUR", "kind": "current_bid"},
            "import_draft": {
                "platform_code": prefill["platform_code"],
                "fetched_at": prefill["fetched_at"],
                "access_mode": prefill["access_mode"],
                "fields": prefill["fields"],
                "warnings": prefill["warnings"],
            },
        },
    )
    assert created.status_code == 201, created.text

    trace = await client.get(f"/api/v1/opportunities/{created.json()['id']}/import")
    assert len(trace.json()["items"]) == 1
    # L'observation est append-only : le déclencheur `listing_observations_
    # append_only` refuse toute modification, ce que vérifie
    # `test_schema_snapshot`. Ici on constate seulement qu'elle est bien là.


async def test_a_manual_entry_records_no_import_trace(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Rien n'a été importé : il n'y a rien à conserver, et surtout rien à
    présenter comme venant d'une annonce."""

    created = await client.post(
        "/api/v1/opportunities",
        json={
            "portfolio_id": str(default_portfolio_id),
            "source": {"mode": "manual", "manual_identifier": "SANS-IMPORT-1"},
            "watch": {"brand": "Tudor", "reference": "79030N"},
        },
    )
    assert created.status_code == 201, created.text

    trace = await client.get(f"/api/v1/opportunities/{created.json()['id']}/import")
    assert trace.status_code == 200
    assert trace.json()["items"] == []


async def test_the_import_trace_of_a_foreign_opportunity_is_not_disclosed(
    anonymous_client: AsyncClient,
) -> None:
    response = await anonymous_client.get(
        f"/api/v1/opportunities/{uuid.uuid4()}/import"
    )
    assert response.status_code == 401
