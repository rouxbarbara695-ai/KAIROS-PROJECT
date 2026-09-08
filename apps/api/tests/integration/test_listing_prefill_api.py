"""Le parcours « je colle un lien », vu de l'API.

Le fil conducteur de ces tests est qu'un échec de récupération **n'est pas une
erreur de la requête** : c'est un résultat, et il doit être aussi utilisable
qu'une réussite. Le lien est conservé, le motif est précis, et le repli est
nommé — sans quoi l'utilisateur recolle son lien en boucle devant un message
générique.

Aucun test ne sort sur le réseau : le récupérateur est remplacé par une
dérogation d'injection. Dépendre d'annonces réelles rendrait la suite rouge le
jour où une montre est vendue.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.api.v1.routes.listings import get_fetcher
from app.collection.ports.fetcher import FetchedPage
from app.main import app
from app.shared.domain.errors import DomainError, ErrorCode

pytestmark = pytest.mark.integration

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "listings"
    / "watchfinder-cartier-santos.html"
)
_LISTING_URL = (
    "https://www.watchfinder.co.uk/watches/cartier/santos/"
    "santos-de-cartier/wssa0096/442565"
)


class _StubFetcher:
    """Récupérateur de test : rend une page figée, ou lève ce qu'on lui dit."""

    def __init__(self, page: FetchedPage | None, error: DomainError | None = None):
        self.page = page
        self.error = error
        self.calls: list[tuple[str, frozenset[str]]] = []

    async def fetch(self, url: str, allowed_hosts: frozenset[str]) -> FetchedPage:
        self.calls.append((url, allowed_hosts))
        if self.error is not None:
            raise self.error
        assert self.page is not None
        return self.page


@pytest_asyncio.fixture
async def stub() -> AsyncIterator[_StubFetcher]:
    page = FetchedPage(
        final_url=_LISTING_URL,
        status_code=200,
        content_type="text/html",
        text=_FIXTURE.read_text(encoding="utf-8"),
    )
    fetcher = _StubFetcher(page)
    app.dependency_overrides[get_fetcher] = lambda: fetcher
    yield fetcher
    app.dependency_overrides.pop(get_fetcher, None)


async def test_a_link_returns_a_draft_to_check(
    client: AsyncClient, stub: _StubFetcher
) -> None:
    response = await client.post("/api/v1/listings/prefill", json={"url": _LISTING_URL})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded"] is True
    assert body["platform_code"] == "watchfinder"
    assert body["access_mode"] == "automatic"

    fields = body["fields"]
    assert fields["brand"]["value"] == "Cartier"
    assert fields["brand"]["provenance"] == "imported"
    assert fields["reference"]["value"] == "WSSA0096"
    # Montant en chaîne décimale, jamais en nombre JSON (règle 2).
    assert fields["price_amount"]["value"] == "7995"
    assert fields["price_currency"]["value"] == "GBP"

    # Ce que la page ne dit pas est explicitement absent, avec sa raison.
    assert fields["calibre"]["provenance"] == "absent"
    assert fields["calibre"]["source"]

    assert any("à confirmer" in warning for warning in body["warnings"])


async def test_the_fetch_stays_inside_the_platform_domains(
    client: AsyncClient, stub: _StubFetcher
) -> None:
    """Le récupérateur reçoit une liste blanche, pas une URL libre."""

    await client.post("/api/v1/listings/prefill", json={"url": _LISTING_URL})

    _, hosts = stub.calls[0]
    assert "watchfinder.co.uk" in hosts
    assert "chrono24.com" not in hosts


async def test_a_protected_platform_is_not_even_attempted(
    client: AsyncClient, stub: _StubFetcher
) -> None:
    """Chrono24 protège ses pages : aucune requête n'est émise.

    La décision se prend avant le réseau. Tenter puis constater le refus
    reviendrait à frapper à une porte dont on sait qu'elle est fermée.
    """

    response = await client.post(
        "/api/v1/listings/prefill",
        json={"url": "https://www.chrono24.fr/rolex/submariner--id123.htm"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded"] is False
    assert body["access_mode"] == "assisted"
    assert body["failure"]["details"]["fallback"] == "assisted_import"
    # Le lien est conservé : l'utilisateur n'a pas à le recoller.
    assert body["url"].startswith("https://www.chrono24.fr/")
    assert stub.calls == []


async def test_a_platform_that_forbids_automation_is_never_called(
    client: AsyncClient, stub: _StubFetcher
) -> None:
    """eBay l'interdit dans ses conditions, faisabilité mise à part."""

    response = await client.post(
        "/api/v1/listings/prefill",
        json={"url": "https://www.ebay.fr/itm/123456789"},
    )

    body = response.json()
    assert body["succeeded"] is False
    assert body["access_mode"] == "forbidden"
    assert body["failure"]["details"]["reason"] == "platform_forbids_automation"
    assert stub.calls == []


async def test_a_refusal_keeps_the_link_and_names_the_fallback(
    client: AsyncClient,
) -> None:
    """Un site indépendant protégé se découvre à la requête, pas avant."""

    blocked = _StubFetcher(
        None,
        DomainError(
            ErrorCode.COLLECTOR_NOT_AUTHORIZED,
            "Cette plateforme protège ses pages contre les accès automatisés.",
            details={"reason": "protected_by_platform", "fallback": "assisted_import"},
        ),
    )
    app.dependency_overrides[get_fetcher] = lambda: blocked
    try:
        response = await client.post(
            "/api/v1/listings/prefill",
            json={"url": "https://boutique.example/montre/1"},
        )
    finally:
        app.dependency_overrides.pop(get_fetcher, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded"] is False
    assert body["url"] == "https://boutique.example/montre/1"
    assert body["failure"]["details"]["fallback"] == "assisted_import"


async def test_the_assisted_import_emits_no_request(client: AsyncClient) -> None:
    """Le repli lit le contenu fourni, sans jamais joindre la plateforme."""

    never = _StubFetcher(None, DomainError(ErrorCode.COLLECTOR_UNAVAILABLE, "jamais"))
    app.dependency_overrides[get_fetcher] = lambda: never
    try:
        response = await client.post(
            "/api/v1/listings/prefill/assisted",
            json={
                "url": "https://www.chrono24.fr/rolex/submariner--id123.htm",
                "content": _FIXTURE.read_text(encoding="utf-8"),
            },
        )
    finally:
        app.dependency_overrides.pop(get_fetcher, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded"] is True
    assert body["access_mode"] == "assisted"
    assert body["platform_code"] == "chrono24"
    # La provenance dit d'où vient la valeur : un import assisté ne se fait
    # jamais passer pour une récupération automatique réussie.
    assert body["fields"]["brand"]["provenance"] == "assisted"
    assert never.calls == []


async def test_pasting_something_that_is_not_a_listing_says_so(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/listings/prefill/assisted",
        json={
            "url": "https://www.chrono24.fr/rolex/submariner--id123.htm",
            "content": "<html><body>Bonjour</body></html>",
        },
    )

    body = response.json()
    assert body["succeeded"] is True  # l'analyse a tourné
    assert all(field["provenance"] == "absent" for field in body["fields"].values())
    assert any("Rien n'a pu être lu" in warning for warning in body["warnings"])


async def test_the_access_mode_is_knowable_before_trying(
    client: AsyncClient,
) -> None:
    """L'interface annonce le repli au moment où le lien est collé."""

    for url, expected in (
        (_LISTING_URL, "automatic"),
        ("https://www.chrono24.fr/x--id1.htm", "assisted"),
        ("https://www.ebay.fr/itm/1", "forbidden"),
    ):
        response = await client.get("/api/v1/listings/access", params={"url": url})
        assert response.status_code == 200, response.text
        assert response.json()["access_mode"] == expected
        assert response.json()["explanation"]


async def test_prefill_requires_a_session(anonymous_client: AsyncClient) -> None:
    response = await anonymous_client.post(
        "/api/v1/listings/prefill", json={"url": _LISTING_URL}
    )
    assert response.status_code == 401


async def test_a_serial_number_never_appears_in_the_response(
    client: AsyncClient,
) -> None:
    """Règle 11, vérifiée sur la réponse complète, pas sur un champ."""

    content = (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Rolex Datejust",'
        '"description":"Série : A1234567, complète."}'
        "</script></head><body></body></html>"
    )
    response = await client.post(
        "/api/v1/listings/prefill/assisted",
        json={"url": "https://boutique.example/m/1", "content": content},
    )

    assert "A1234567" not in response.text
