"""Adaptateur eBay : formation des requêtes, lecture des réponses, arrêts.

`httpx.MockTransport` fait passer les requêtes par la **vraie** bibliothèque
(en-têtes, encodage, corps de formulaire) mais les réponses sont simulées : ce
fichier prouve la logique de l'adaptateur, **pas** l'accès réel à eBay. Cet
accès ne se prouve qu'avec de vrais identifiants (`python -m
app.market_search.probe`).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.market_search.adapters.ebay_browse import EbayBrowseSource, parse_item
from app.market_search.domain.candidate import SearchQuery
from app.market_search.domain.policy import SearchPolicy

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
QUERY = SearchQuery(brand="Omega", reference="1561.61.00", model="Constellation")


def item(item_id: str = "v1|111|0", **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "itemId": item_id,
        "legacyItemId": "111",
        "title": "Omega Constellation 1561.61.00 quartz acier",
        "price": {"value": "850.00", "currency": "EUR"},
        "buyingOptions": ["FIXED_PRICE", "BEST_OFFER"],
        "itemWebUrl": "https://www.ebay.fr/itm/111?hash=item1&amdata=tracking",
        "itemCreationDate": "2026-09-20T10:00:00.000Z",
        "condition": "Pre-owned",
        "itemLocation": {"country": "FR"},
        "shippingOptions": [
            {
                "shippingCostType": "FIXED",
                "shippingCost": {"value": "9.90", "currency": "EUR"},
            },
            {
                "shippingCostType": "FIXED",
                "shippingCost": {"value": "19.90", "currency": "EUR"},
            },
        ],
        # Données personnelles : ne doivent jamais atteindre le candidat.
        "seller": {"username": "vendeur_prive", "feedbackPercentage": "99.1"},
    }
    base.update(overrides)
    return base


class FakeEbay:
    def __init__(self, handler: Any = None) -> None:
        self.calls: list[httpx.Request] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(
                200, json={"access_token": "jeton-test", "expires_in": 7200}
            )
        if self._handler:
            return self._handler(request)
        return httpx.Response(200, json={"itemSummaries": [item()]})

    def searches(self) -> list[httpx.Request]:
        return [c for c in self.calls if "item_summary" in c.url.path]


async def run(
    fake: FakeEbay,
    *,
    client_id: str | None = "id-test",
    client_secret: str | None = "secret-test",
    policy: SearchPolicy | None = None,
    marketplaces: list[str] | None = None,
):
    async def no_sleep(_: float) -> None:
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as client:
        source = EbayBrowseSource(
            client_id=client_id,
            client_secret=client_secret,
            marketplaces=marketplaces or ["EBAY_FR", "EBAY_DE"],
            policy=policy or SearchPolicy(),
            client=client,
            sleep=no_sleep,
            clock=lambda: NOW,
        )
        return await source.search(QUERY)


async def test_unconfigured_source_emits_no_request() -> None:
    fake = FakeEbay()
    outcome = await run(fake, client_id=None, client_secret=None)
    assert outcome.status == "not_configured"
    assert fake.calls == []
    assert outcome.candidates == []


async def test_token_request_uses_client_credentials_and_basic_auth() -> None:
    fake = FakeEbay()
    await run(fake)
    token_call = fake.calls[0]
    assert (
        token_call.headers["authorization"]
        == "Basic " + base64.b64encode(b"id-test:secret-test").decode()
    )
    body = parse_qs(token_call.content.decode())
    assert body["grant_type"] == ["client_credentials"]
    assert body["scope"] == ["https://api.ebay.com/oauth/api_scope"]


async def test_search_uses_bearer_marketplace_and_both_spellings() -> None:
    fake = FakeEbay()
    outcome = await run(fake)
    searches = fake.searches()
    assert {s.headers["x-ebay-c-marketplace-id"] for s in searches} == {
        "EBAY_FR",
        "EBAY_DE",
    }
    assert all(s.headers["authorization"] == "Bearer jeton-test" for s in searches)
    queries = {s.url.params["q"] for s in searches}
    assert queries == {"Omega 1561.61.00", "Omega 15616100"}
    assert outcome.status == "ok"
    # Chaque requête émise est consignée : c'est la preuve de ce qui est interrogé.
    assert len(outcome.requests) == 1 + len(searches)
    assert all(r.http_status == 200 for r in outcome.requests)


async def test_candidate_carries_price_nature_and_no_personal_data() -> None:
    fake = FakeEbay()
    outcome = await run(fake, marketplaces=["EBAY_FR"])
    c = outcome.candidates[0]
    assert (c.amount, c.currency, c.price_kind) == (Decimal("850.00"), "EUR", "asking")
    assert c.offers_accepted is True
    assert c.shipping_amount == Decimal("9.90")  # le moins cher
    assert c.url == "https://www.ebay.fr/itm/111"  # sans paramètres de suivi
    assert c.country == "FR"
    assert "vendeur_prive" not in repr(c)
    assert not hasattr(c, "seller")


def test_auction_is_a_current_bid_with_its_end_time() -> None:
    parsed = parse_item(
        item(
            buyingOptions=["AUCTION"],
            price={"value": "500", "currency": "EUR"},
            currentBidPrice={"value": "620.00", "currency": "EUR"},
            bidCount=7,
            itemEndDate="2026-09-30T18:00:00.000Z",
        ),
        "EBAY_FR",
        NOW,
    )
    assert parsed is not None
    assert parsed.price_kind == "current_bid"
    assert parsed.amount == Decimal("620.00")
    assert parsed.bid_count == 7
    assert parsed.ends_at == datetime(2026, 9, 30, 18, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "broken",
    [
        {"price": {"value": "abc", "currency": "EUR"}},
        {"price": {"value": "10", "currency": "EURO"}},
        {"price": None},
        {"itemId": None},
        {"title": None},
        {"price": {"value": "-5", "currency": "EUR"}},
    ],
)
def test_unreadable_item_is_dropped_not_completed(broken: dict[str, Any]) -> None:
    assert parse_item(item(**broken), "EBAY_FR", NOW) is None


async def test_next_page_is_followed_within_the_page_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        payload: dict[str, Any] = {"itemSummaries": [item(f"v1|{offset}|0")]}
        if offset == 0:
            payload["next"] = "https://api.ebay.com/next"
        return httpx.Response(200, json=payload)

    fake = FakeEbay(handler)
    outcome = await run(
        fake, marketplaces=["EBAY_FR"], policy=SearchPolicy(page_size=50)
    )
    offsets = sorted(int(s.url.params["offset"]) for s in fake.searches())
    assert offsets == [0, 0, 50, 50]  # deux écritures × deux pages
    assert outcome.status == "ok"


@pytest.mark.parametrize(
    ("status", "expected"), [(403, "blocked"), (401, "blocked"), (429, "rate_limited")]
)
async def test_explicit_refusal_stops_the_source_without_retry(
    status: int, expected: str
) -> None:
    fake = FakeEbay(lambda request: httpx.Response(status, json={"errors": []}))
    outcome = await run(fake)
    assert outcome.status == expected
    # Un seul appel de recherche : aucune boucle de nouvelle tentative.
    assert len(fake.searches()) == 1
    assert outcome.candidates == []
    assert outcome.message


async def test_refusal_keeps_candidates_already_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["x-ebay-c-marketplace-id"] == "EBAY_DE":
            return httpx.Response(429)
        return httpx.Response(200, json={"itemSummaries": [item()]})

    outcome = await run(FakeEbay(handler))
    assert outcome.status == "rate_limited"
    assert outcome.candidates, "un échec n'efface pas les données valides"


async def test_server_error_on_one_marketplace_does_not_stop_the_others() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["x-ebay-c-marketplace-id"] == "EBAY_DE":
            return httpx.Response(503)
        return httpx.Response(200, json={"itemSummaries": [item()]})

    outcome = await run(FakeEbay(handler))
    assert outcome.status == "ok"
    assert outcome.candidates
    assert "EBAY_DE" in (outcome.message or "")


async def test_rejected_credentials_emit_no_search() -> None:
    def token_refused(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    async def no_sleep(_: float) -> None:
        return None

    calls: list[httpx.Request] = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return token_refused(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        source = EbayBrowseSource(
            client_id="a",
            client_secret="b",
            marketplaces=["EBAY_FR"],
            policy=SearchPolicy(),
            client=client,
            sleep=no_sleep,
        )
        outcome = await source.search(QUERY)
    assert outcome.status == "blocked"
    assert len(calls) == 1
    assert "identifiants" in (outcome.message or "")
    assert outcome.message != "b"  # le secret n'est jamais recopié


async def test_request_budget_is_enforced() -> None:
    fake = FakeEbay()
    outcome = await run(fake, policy=SearchPolicy(max_requests_per_run=3))
    assert outcome.status == "budget_exhausted"
    assert len(outcome.requests) == 3
    assert "partiels" in (outcome.message or "")


async def test_network_failure_is_reported_not_raised() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("réseau coupé")

    fake = FakeEbay(boom)
    outcome = await run(fake)
    assert outcome.status == "error"
    assert outcome.candidates == []


def test_ebay_credentials_are_never_sent_over_plain_http_outside_local() -> None:
    from pydantic import ValidationError

    from app.shared.config import Settings

    common = {
        "database_url": "postgresql+psycopg://x",
        "redis_url": "redis://x",
        "cursor_secret": "s",
        "cors_allowed_origins": ["https://kairos.example"],
    }
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            ebay_api_base_url="http://127.0.0.1:9099",
            **common,  # type: ignore[arg-type]
        )
    # En local, un serveur d'essai en clair reste permis (parcours navigateur).
    local = Settings(
        environment="local",
        ebay_api_base_url="http://127.0.0.1:9099",
        **common,  # type: ignore[arg-type]
    )
    assert local.ebay_api_base_url == "http://127.0.0.1:9099"
