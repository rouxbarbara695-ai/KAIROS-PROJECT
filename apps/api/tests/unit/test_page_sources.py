"""Sources de pages publiques : lecture de vraies pages, arrêts, politesse.

Les fichiers de `tests/fixtures/sources/` sont des **pages réelles** relevées le
30 septembre 2026 (numéros de série de tiers masqués) : le parseur est éprouvé sur
ce que les sites servent vraiment, pas sur un HTML imaginé. Les requêtes passent
par la vraie bibliothèque HTTP (`httpx.MockTransport`), mais les réponses sont
rejouées : ces tests prouvent la lecture et la politesse, **pas l'accès réel**,
qui se prouve avec `python -m app.market_search.probe`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.market_search.adapters import antiquorum, sworders, vintage_watch_agency
from app.market_search.adapters.antiquorum import AntiquorumSource
from app.market_search.adapters.polite_http import PoliteClient, SourceStop
from app.market_search.adapters.sworders import SwordersSource
from app.market_search.adapters.ucp_catalog import UcpCatalogSource, parse_product
from app.market_search.adapters.vintage_watch_agency import VintageWatchAgencySource
from app.market_search.domain.candidate import SearchQuery, SourceOutcome
from app.market_search.domain.money import parse_amount
from app.market_search.domain.policy import SearchPolicy
from app.market_search.domain.screening import screen
from app.shared.infrastructure.fx_ecb import parse_ecb_rates

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
POLICY = SearchPolicy(page_source_min_delay_s=0)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


async def no_sleep(_: float) -> None:
    return None


def accepted(candidates, brand, reference, model=None):
    return [
        c
        for c in candidates
        if screen(
            c, brand=brand, reference=reference, model=model, policy=POLICY
        ).accepted
    ]


# --- Montants ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("£3,500", (Decimal("3500"), "GBP")),
        ("CHF 7,750", (Decimal("7750"), "CHF")),
        ("HKD 75,000", (Decimal("75000"), "HKD")),
        ("€ 1.520", (Decimal("1520"), "EUR")),
        ("€ 1.520", (Decimal("1520"), "EUR")),
        ("1 234,50 €", (Decimal("1234.50"), "EUR")),
        ("USD 4,080", (Decimal("4080"), "USD")),
    ],
)
def test_amounts_are_read_with_their_currency(text: str, expected) -> None:
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", ["$1,200", "sur demande", "1,2,3", "12,34,567", ""])
def test_ambiguous_or_missing_amounts_are_refused(text: str) -> None:
    # « $ » seul est ambigu (USD, HKD, CAD…) : jamais interprété.
    assert parse_amount(text) is None


# --- Antiquorum ---------------------------------------------------------------


def test_antiquorum_finds_the_exact_lots_on_a_real_results_page() -> None:
    found, total, cards = antiquorum.parse_results(
        fixture("antiquorum-reverso-duetto.html"), NOW
    )
    assert (total, cards, len(found)) == (19, 19, 16)  # 3 lots sans prix publié
    exact = accepted(found, "Jaeger-LeCoultre", "266.1.44", "Reverso Duetto")
    assert {(c.amount, c.currency, c.sold_at.year) for c in exact} == {
        (Decimal("75000"), "HKD", 2025),
        (Decimal("7750"), "CHF", 2013),
        (Decimal("15600"), "USD", 2009),
    }
    # Le voisin « 266.5.44 » n'est pas la référence : jamais substitué.
    assert all("266-5-44" not in c.url for c in exact)


def test_antiquorum_prices_are_hammer_results_with_unknown_fees() -> None:
    found, _, _ = antiquorum.parse_results(
        fixture("antiquorum-reverso-duetto.html"), NOW
    )
    for candidate in found:
        assert candidate.price_kind == "hammer"
        assert candidate.market_status == "sold"
        assert candidate.fees_status == "unknown"
        assert candidate.sold_at is not None


def test_antiquorum_ignores_the_structured_price_which_is_the_low_estimate() -> None:
    """Le lot de 2025 est adjugé 75 000 HKD ; `schema:price` y vaut 40 000, son
    estimation basse. Le prix de vente est le seul montant repris."""

    found, _, _ = antiquorum.parse_results(
        fixture("antiquorum-reverso-duetto.html"), NOW
    )
    lot = next(c for c in found if "lot-378-277" in c.url)
    assert lot.amount == Decimal("75000")


def test_antiquorum_never_keeps_case_or_movement_numbers() -> None:
    found, _, _ = antiquorum.parse_results(
        fixture("antiquorum-reverso-duetto.html"), NOW
    )
    for candidate in found:
        text = f"{candidate.title} {candidate.description}"
        assert "Case No" not in text and "Movement No" not in text


async def _run_source(source, query, routes):
    def handler(request: httpx.Request) -> httpx.Response:
        for matcher, response in routes:
            if matcher(request):
                return response(request) if callable(response) else response
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        instance = source(client, POLICY, sleep=no_sleep)
        return await instance.search(query)


ROBOTS_OPEN = (
    lambda r: r.url.path == "/robots.txt",
    httpx.Response(200, text="User-agent: *\n"),
)


async def test_antiquorum_source_discovers_by_brand_and_model_then_filters() -> None:
    routes = [
        ROBOTS_OPEN,
        (
            lambda r: r.url.path == "/en/lots",
            httpx.Response(200, text=fixture("antiquorum-reverso-duetto.html")),
        ),
    ]
    outcome = await _run_source(
        AntiquorumSource,
        SearchQuery("Jaeger-LeCoultre", "266.1.44", "Reverso Duetto"),
        routes,
    )
    assert outcome.status == "ok" and outcome.complete
    assert [r.http_status for r in outcome.requests] == [200, 200]
    assert len(accepted(outcome.candidates, "Jaeger-LeCoultre", "266.1.44")) == 3


async def test_antiquorum_partial_read_is_declared_incomplete() -> None:
    page = "<div>AUCTIONS 580 lots</div>" + fixture("antiquorum-reverso-duetto.html")
    routes = [
        ROBOTS_OPEN,
        (lambda r: r.url.path == "/en/lots", httpx.Response(200, text=page)),
    ]
    outcome = await _run_source(
        AntiquorumSource, SearchQuery("Omega", "1561.61.00", "Constellation"), routes
    )
    assert outcome.complete is False
    assert "partiels" in (outcome.message or "")
    assert (
        len([r for r in outcome.requests if "page" in r.label])
        == POLICY.max_result_pages
    )


# --- Sworders -----------------------------------------------------------------


def test_sworders_result_page_then_lot_page_give_the_exact_reference() -> None:
    cards = sworders.parse_results(fixture("sworders-search-reverso-duetto.html"))
    assert [c.lot_id for c in cards] == ["546323"]
    candidate = sworders.parse_lot(fixture("sworders-lot-290.html"), cards[0], NOW)
    assert candidate is not None
    assert (candidate.amount, candidate.currency) == (Decimal("3500"), "GBP")
    assert candidate.sold_at == datetime(2025, 11, 18, tzinfo=UTC)
    assert candidate.price_kind == "hammer" and candidate.fees_status == "unknown"
    # La référence n'est PAS dans le titre : elle vient de la description.
    assert "266.1.44" not in candidate.title
    assert accepted([candidate], "Jaeger-LeCoultre", "266.1.44")


def test_sworders_serial_number_is_removed_before_storage() -> None:
    cards = sworders.parse_results(fixture("sworders-search-reverso-duetto.html"))
    candidate = sworders.parse_lot(fixture("sworders-lot-290.html"), cards[0], NOW)
    assert candidate is not None and candidate.description is not None
    assert "0000000" not in candidate.description
    assert "numéro de série retiré" in candidate.description


async def test_sworders_source_respects_the_crawl_delay_of_its_robots_txt() -> None:
    waits: list[float] = []

    async def record_sleep(seconds: float) -> None:
        waits.append(seconds)

    ticks = iter(
        range(0, 10_000, 1)
    )  # horloge qui n'avance que d'une seconde par lecture

    routes = [
        (
            lambda r: r.url.path == "/robots.txt",
            httpx.Response(
                200, text="User-agent: *\nDisallow: /account/*\ncrawl-delay: 10\n"
            ),
        ),
        (
            lambda r: r.url.path == "/auction/search",
            httpx.Response(200, text=fixture("sworders-search-reverso-duetto.html")),
        ),
        (
            lambda r: r.url.path.startswith("/auction/lot/"),
            httpx.Response(200, text=fixture("sworders-lot-290.html")),
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        for matcher, response in routes:
            if matcher(request):
                return response
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = SwordersSource(
            client, POLICY, sleep=record_sleep, monotonic=lambda: float(next(ticks))
        )
        outcome = await source.search(
            SearchQuery("Jaeger-LeCoultre", "266.1.44", "Reverso Duetto")
        )
    assert outcome.status == "ok" and len(outcome.candidates) == 1
    # Chaque attente vaut au moins le crawl-delay publié, moins le temps écoulé.
    assert waits and all(w >= 8 for w in waits)


# --- Vintage Watch Agency -------------------------------------------------------


def test_vwa_exact_listing_is_read_from_its_search_card_and_product_page() -> None:
    cards = vintage_watch_agency.parse_results(fixture("vwa-search-1561.html"))
    assert len(cards) == 1
    assert cards[0].price == "€ 1.520"  # le prix soldé, pas l'ancien (1.610)
    fields, status = vintage_watch_agency.parse_detail(fixture("vwa-product-1561.html"))
    assert status == "active"
    assert fields["condition"] == "Very good (4 of 5)"
    assert fields["case"] == "Steel" and fields["movement type"].startswith("Quartz")


async def test_vwa_source_produces_an_asking_price_in_euros() -> None:
    routes = [
        ROBOTS_OPEN,
        (
            lambda r: r.url.path == "/search-results.html",
            httpx.Response(200, text=fixture("vwa-search-1561.html")),
        ),
        (
            lambda r: r.url.path.endswith("-pv-1448006.html"),
            httpx.Response(200, text=fixture("vwa-product-1561.html")),
        ),
    ]
    outcome = await _run_source(
        VintageWatchAgencySource,
        SearchQuery("Omega", "1561.61.00", "Constellation"),
        routes,
    )
    (candidate,) = outcome.candidates
    assert (candidate.amount, candidate.currency) == (Decimal("1520"), "EUR")
    assert candidate.price_kind == "asking" and candidate.market_status == "active"
    assert candidate.fees_status == "not_applicable"
    assert accepted([candidate], "Omega", "1561.61.00", "Constellation")


async def test_vwa_search_with_no_result_is_ok_and_empty_not_an_error() -> None:
    empty = fixture("vwa-search-1561.html").split("<div id='p_i_")[0] + "</html>"
    routes = [
        ROBOTS_OPEN,
        (
            lambda r: r.url.path == "/search-results.html",
            httpx.Response(200, text=empty),
        ),
    ]
    outcome = await _run_source(
        VintageWatchAgencySource, SearchQuery("Cartier", "W1002253", None), routes
    )
    assert outcome.status == "ok" and outcome.candidates == []


# --- Catalogue UCP (Phigora) ------------------------------------------------------


def _ucp_products(name: str) -> list[dict]:
    return json.loads(fixture(name))["result"]["structuredContent"]["products"]


def test_ucp_sold_out_product_is_read_as_sold_and_then_not_retained() -> None:
    product = _ucp_products("phigora-search-omega-1561.json")[0]
    candidate = parse_product(product, source="phigora", country="US", now=NOW)
    assert candidate is not None
    assert candidate.market_status == "sold"
    assert (candidate.amount, candidate.currency) == (Decimal("1699"), "USD")
    verdict = screen(
        candidate, brand="Omega", reference="1561.61.00", model=None, policy=POLICY
    )
    # Ancien prix demandé, non daté : montré, jamais compté dans l'estimation.
    assert not verdict.accepted and verdict.code == "sold_out_price_undated"


def test_ucp_never_reads_tags_which_can_carry_a_serial_number() -> None:
    for name in ("phigora-search-omega-1561.json", "phigora-search-speedmaster.json"):
        for product in _ucp_products(name):
            candidate = parse_product(product, source="phigora", country="US", now=NOW)
            if candidate is not None:
                assert "Serial" not in repr(candidate)


def test_ucp_prices_are_converted_from_minor_units() -> None:
    product = _ucp_products("phigora-search-speedmaster.json")[0]
    candidate = parse_product(product, source="phigora", country="US", now=NOW)
    assert candidate is not None
    assert candidate.amount * 100 == product["price_range"]["min"]["amount"]


def _ucp_handler(profile: dict | None, search: dict | None, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/ucp":
            return httpx.Response(status, json=profile or {})
        if request.method == "POST":
            body = json.loads(request.content)
            # Le profil d'agent de KAIROS est joint à chaque requête.
            profile_url = body["params"]["arguments"]["meta"]["ucp-agent"]["profile"]
            assert profile_url.endswith("kairos-agent-profile.json")
            return httpx.Response(200, json=search)
        return httpx.Response(404)

    return handler


BUSINESS_PROFILE = {
    "ucp": {
        "version": "2026-08-25",
        "services": {
            "dev.ucp.shopping": [
                {"transport": "mcp", "endpoint": "https://shop.example/api/ucp/mcp"}
            ]
        },
        "capabilities": {
            "dev.ucp.shopping.catalog.search": [{"version": "2026-08-25"}]
        },
    }
}


async def _ucp(handler, query=SearchQuery("Omega", "3570.50.00", "Speedmaster")):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = UcpCatalogSource(
            client,
            POLICY,
            name="phigora",
            site="https://www.phigora.com",
            country="US",
            sleep=no_sleep,
        )
        return await source.search(query)


async def test_ucp_source_reads_the_profile_then_searches_the_catalog() -> None:
    search = json.loads(fixture("phigora-search-speedmaster.json"))
    outcome = await _ucp(_ucp_handler(BUSINESS_PROFILE, search))
    assert outcome.status == "ok"
    assert [r.label.split(" « ")[0] for r in outcome.requests][:2] == [
        "Profil UCP de https://www.phigora.com",
        "UCP search_catalog",
    ]
    assert outcome.candidates


async def test_ucp_source_refuses_a_shop_without_catalog_search() -> None:
    profile = {"ucp": {**BUSINESS_PROFILE["ucp"], "capabilities": {}}}
    outcome = await _ucp(_ucp_handler(profile, {}))
    assert outcome.status == "blocked"
    assert "catalog.search" in (outcome.message or "")


async def test_ucp_source_reports_a_server_refusal_with_its_code() -> None:
    error = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {
            "code": -32001,
            "message": "UCP discovery failed",
            "data": {"code": "profile_malformed", "content": "Invalid content type"},
        },
    }
    outcome = await _ucp(_ucp_handler(BUSINESS_PROFILE, error))
    assert outcome.status == "error"
    assert "profile_malformed" in (outcome.message or "")


# --- Politesse ------------------------------------------------------------------


async def _polite(handler, *, policy=POLICY):
    outcome = SourceOutcome(source="test", status="ok")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return PoliteClient(client, outcome, policy, sleep=no_sleep), outcome, client


async def test_a_path_disallowed_by_robots_txt_is_never_requested() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, text="secret")

    http, _, client = await _polite(handler)
    with pytest.raises(SourceStop) as stop:
        await http.get("https://x.example/private/page", label="t")
    await client.aclose()
    assert stop.value.status == "blocked"
    assert seen == ["/robots.txt"]


@pytest.mark.parametrize("status", [401, 403])
async def test_unreadable_robots_txt_stops_the_source(status: int) -> None:
    http, outcome, client = await _polite(lambda r: httpx.Response(status))
    with pytest.raises(SourceStop) as stop:
        await http.get("https://x.example/page", label="t")
    await client.aclose()
    assert stop.value.status == "blocked"
    assert [r.http_status for r in outcome.requests] == [status]  # aucune page requêtée


async def test_a_challenge_header_is_a_refusal_never_bypassed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="")
        return httpx.Response(200, headers={"cf-mitigated": "challenge"}, text="…")

    http, _, client = await _polite(handler)
    with pytest.raises(SourceStop) as stop:
        await http.get("https://x.example/page", label="t")
    await client.aclose()
    assert stop.value.status == "blocked" and "défi anti-robot" in stop.value.message


async def test_http_429_is_rate_limited() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)  # pas de robots.txt : rien n'est interdit
        return httpx.Response(429)

    http, _, client = await _polite(handler)
    with pytest.raises(SourceStop) as stop:
        await http.get("https://x.example/page", label="t")
    await client.aclose()
    assert stop.value.status == "rate_limited"


async def test_request_budget_stops_a_page_source() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404 if request.url.path == "/robots.txt" else 200, text="ok"
        )

    http, outcome, client = await _polite(
        handler,
        policy=SearchPolicy(page_source_min_delay_s=0, page_source_max_requests=3),
    )
    await http.get("https://x.example/a", label="a")
    await http.get("https://x.example/b", label="b")
    with pytest.raises(SourceStop) as stop:
        await http.get("https://x.example/c", label="c")
    await client.aclose()
    assert stop.value.status == "budget_exhausted" and outcome.complete is False


async def test_a_source_never_raises_even_on_a_broken_page() -> None:
    routes = [
        ROBOTS_OPEN,
        (
            lambda r: r.url.path == "/en/lots",
            httpx.Response(200, text="<html>ne ressemble à rien</html>"),
        ),
    ]
    outcome = await _run_source(
        AntiquorumSource, SearchQuery("Omega", "1561.61.00", "Constellation"), routes
    )
    assert outcome.status == "ok" and outcome.candidates == []


async def test_unreachable_site_is_an_error_status() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("réseau coupé")

    outcome = await _run_source(
        AntiquorumSource,
        SearchQuery("Omega", "1561.61.00", None),
        [(lambda r: True, boom)],
    )
    assert outcome.status == "error" and outcome.candidates == []


# --- Taux de change de la BCE -------------------------------------------------------


def test_ecb_daily_rates_are_read_with_their_reference_date() -> None:
    day, rates = parse_ecb_rates(fixture("ecb-daily.xml"))
    assert day == "2026-09-30"
    assert rates["USD"] == Decimal("1.1355") and rates["GBP"] == Decimal("0.85463")
