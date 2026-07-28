from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

_HEADER = (
    "source_name,price_kind,amount,currency,source_reliability,"
    "market_status,box,papers,seller_fingerprint"
)


async def _opportunity(client: AsyncClient, portfolio_id: uuid.UUID, ref: str) -> str:
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
    return response.json()["id"]


async def test_valid_rows_are_imported(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity_id = await _opportunity(client, default_portfolio_id, "IMP-001")
    csv_content = "\n".join(
        [
            _HEADER,
            "Chrono24,asking,3000.00,EUR,a,active,oui,oui,vendeur-1",
            "Catawiki,hammer,3150.50,EUR,b,sold,1,0,vendeur-2",
        ]
    )

    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/comparables/import",
        json={"content": csv_content},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"imported": 2, "rejected": []}

    listed = await client.get(f"/api/v1/opportunities/{opportunity_id}/comparables")
    assert len(listed.json()["items"]) == 2


async def test_faulty_rows_are_reported_without_losing_the_others(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Un fichier partiellement erroné ne doit pas faire perdre la saisie déjà
    correcte : les lignes valides passent, les autres sont rapportées."""

    opportunity_id = await _opportunity(client, default_portfolio_id, "IMP-002")
    csv_content = "\n".join(
        [
            _HEADER,
            "Chrono24,asking,3000.00,EUR,a,active,oui,oui,v1",
            ",asking,3000.00,EUR,a,active,oui,oui,v2",
            "Catawiki,asking,pas-un-montant,EUR,a,active,oui,oui,v3",
            "Watchfinder,asking,3300.00,EUR,z,active,oui,oui,v4",
            "Boutique,asking,3400.00,EUR,c,active,peut-etre,oui,v5",
            "Chrono24,asking,3500.00,EUR,b,active,non,non,v6",
        ]
    )

    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/comparables/import",
        json={"content": csv_content},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["imported"] == 2
    assert [row["line"] for row in body["rejected"]] == [3, 4, 5, 6]
    assert all(row["error"] for row in body["rejected"])

    listed = await client.get(f"/api/v1/opportunities/{opportunity_id}/comparables")
    assert len(listed.json()["items"]) == 2


async def test_unknown_columns_are_ignored(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    opportunity_id = await _opportunity(client, default_portfolio_id, "IMP-003")
    csv_content = "\n".join(
        [
            _HEADER + ",commentaire_interne",
            "Chrono24,asking,3000.00,EUR,a,active,oui,oui,v1,à vérifier",
        ]
    )

    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/comparables/import",
        json={"content": csv_content},
    )
    assert response.json()["imported"] == 1


async def test_unrecognised_header_names_what_is_missing(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Un fichier inexploitable doit dire pourquoi, pas répondre « 0 importé,
    0 rejeté » et laisser deviner."""

    opportunity_id = await _opportunity(client, default_portfolio_id, "IMP-004")
    response = await client.post(
        f"/api/v1/opportunities/{opportunity_id}/comparables/import",
        json={"content": "colonne_inconnue,autre\nvaleur,valeur"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert "source_name" in error["details"]["missing_columns"]
    assert "amount" in error["details"]["missing_columns"]


async def test_import_into_foreign_opportunity_is_not_disclosed(
    client: AsyncClient,
) -> None:
    response = await client.post(
        f"/api/v1/opportunities/{uuid.uuid4()}/comparables/import",
        json={"content": _HEADER + "\nChrono24,asking,3000.00,EUR,a,active,oui,oui,v1"},
    )
    assert response.status_code == 404


async def test_imported_comparables_feed_the_valuation(
    client: AsyncClient, default_portfolio_id: uuid.UUID
) -> None:
    """Bout en bout : un CSV importé doit suffire à produire une cote."""

    opportunity_id = await _opportunity(client, default_portfolio_id, "IMP-005")
    csv_content = "\n".join(
        [
            _HEADER,
            "Chrono24,asking,3000.00,EUR,a,active,oui,oui,v1",
            "Catawiki,asking,3100.00,EUR,a,active,oui,oui,v2",
            "Watchfinder,asking,3200.00,EUR,b,active,oui,oui,v3",
        ]
    )
    await client.post(
        f"/api/v1/opportunities/{opportunity_id}/comparables/import",
        json={"content": csv_content},
    )

    valuation = await client.post(f"/api/v1/opportunities/{opportunity_id}/valuations")
    assert valuation.status_code == 201, valuation.text
    assert valuation.json()["explanation"]["comparables_used"] == 3
