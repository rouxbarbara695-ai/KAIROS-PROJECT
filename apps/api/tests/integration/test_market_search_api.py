"""Recherche autonome de comparables : du déclenchement à l'estimation.

Les sources sont **simulées** : ces tests prouvent la logique de KAIROS (contrôle
d'identité, déduplication, provenance, cache, recalcul, échecs par source), pas
l'accès réel à une place de marché. Cet accès se prouve avec de vrais
identifiants (`python -m app.market_search.probe`).

Ce qu'ils défendent :

- **aucune substitution silencieuse** : un voisin de référence ne devient jamais
  un comparable ;
- **la nature du prix** : prix demandé et enchère en cours ne sont jamais des
  ventes, et l'écran en reçoit la mention ;
- **l'échec d'une source ne prouve rien** et n'arrête pas les autres ;
- **la sobriété** : une recherche fraîche est réutilisée, le quota est gardé.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import app
from app.market_search.application.runtime import SearchRuntime, get_search_runtime
from app.market_search.domain.candidate import (
    Candidate,
    RequestRecord,
    SearchQuery,
    SourceOutcome,
)
from app.market_search.domain.policy import SearchPolicy
from app.market_search.ports.source import ComparableSource

pytestmark = pytest.mark.integration


def _now() -> datetime:
    return datetime.now(UTC)


def cand(
    title: str,
    amount: str = "3400.00",
    *,
    external_id: str,
    kind: str = "asking",
    ends_in_hours: float | None = None,
    bids: int | None = None,
) -> Candidate:
    return Candidate(
        source="ebay",
        external_id=external_id,
        title=title,
        url=f"https://www.ebay.fr/itm/{external_id.split('|')[1]}",
        amount=Decimal(amount),
        currency="EUR",
        price_kind=kind,  # type: ignore[arg-type]
        observed_at=_now(),
        ends_at=None
        if ends_in_hours is None
        else _now() + timedelta(hours=ends_in_hours),
        bid_count=bids,
        country="FR",
        condition_text="Pre-owned",
        marketplace="EBAY_FR",
    )


EXACT_A = cand("Tudor Black Bay 79030N acier neuf", "3400.00", external_id="v1|1|0")
EXACT_B = cand("TUDOR Black Bay 79030N full set", "3550.00", external_id="v1|2|0")
NEIGHBOUR = cand("Tudor Black Bay 79230N bleu", "3300.00", external_id="v1|3|0")
PARTS = cand("Tudor 79030N pour pièces", "600.00", external_id="v1|4|0")


class FakeSource:
    def __init__(
        self,
        outcome: SourceOutcome,
        *,
        name: str = "ebay",
        configured: bool = True,
    ) -> None:
        self.name = name
        self._outcome = outcome
        self._configured = configured
        self.calls = 0

    def is_configured(self) -> bool:
        return self._configured

    async def search(self, query: SearchQuery) -> SourceOutcome:
        self.calls += 1
        assert (query.brand, query.reference) == ("Tudor", "79030N")
        return copy.deepcopy(self._outcome)


def ok(*candidates: Candidate) -> SourceOutcome:
    return SourceOutcome(
        source="ebay",
        status="ok",
        candidates=list(candidates),
        requests=[
            RequestRecord("jeton OAuth", 200, 0.2),
            RequestRecord("EBAY_FR « Tudor 79030N » (page 1)", 200, 0.4),
        ],
    )


def fx_rates_fake(rates: dict[str, str], calls: list[set[str]] | None = None):
    """Faux relevé de la BCE : insère les taux demandés qu'il connaît."""

    async def refresh(session: AsyncSession, currencies: set[str]) -> int:
        from app.shared.infrastructure.db.models.reference_data import FxRate

        if calls is not None:
            calls.append(set(currencies))
        added = 0
        for currency in sorted(currencies):
            if currency in rates:
                session.add(
                    FxRate(
                        base_currency=currency,
                        quote_currency="EUR",
                        rate=Decimal(rates[currency]),
                        observed_at=datetime.now(UTC),
                        source_name="BCE (référence du 2026-09-30)",
                    )
                )
                added += 1
        await session.commit()
        return added

    return refresh


@pytest.fixture
def install(_engine):
    def _install(*sources: ComparableSource, fx_refresh=None) -> list[ComparableSource]:
        factory = async_sessionmaker(bind=_engine, expire_on_commit=False)

        @asynccontextmanager
        async def sources_factory(
            settings, policy
        ) -> AsyncIterator[list[ComparableSource]]:
            yield list(sources)

        extra = {"fx_refresh": fx_refresh} if fx_refresh else {}
        runtime = SearchRuntime(
            session_factory=lambda: factory,
            sources=sources_factory,
            policy=SearchPolicy(delay_between_requests_s=0),
            **extra,
        )
        app.dependency_overrides[get_search_runtime] = lambda: runtime
        return list(sources)

    return _install


async def _opportunity(
    client: AsyncClient, portfolio_id: uuid.UUID, ref: str, *, confirm: bool = True
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
    if not confirm:
        return created
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


async def _latest(client: AsyncClient, opportunity_id: str) -> dict[str, object]:
    response = await client.get(
        f"/api/v1/opportunities/{opportunity_id}/market-searches/latest"
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _comparables(
    client: AsyncClient, opportunity_id: str
) -> list[dict[str, object]]:
    response = await client.get(f"/api/v1/opportunities/{opportunity_id}/comparables")
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _count(db_session: AsyncSession, table: str, opportunity_id: str) -> int:
    return (
        await db_session.execute(
            text(f"select count(*) from {table} where opportunity_id = :id"),  # noqa: S608
            {"id": opportunity_id},
        )
    ).scalar_one()


# --- Le parcours : confirmer la référence suffit ---------------------------


async def test_confirming_the_reference_searches_and_feeds_the_engine(
    client: AsyncClient,
    db_session: AsyncSession,
    default_portfolio_id: uuid.UUID,
    install,
) -> None:
    source = FakeSource(ok(EXACT_A, EXACT_B, NEIGHBOUR, PARTS))
    install(source)

    opportunity = await _opportunity(client, default_portfolio_id, "MS-001")
    latest = await _latest(client, opportunity["id"])

    run = latest["run"]
    assert run["status"] == "succeeded"
    assert run["trigger_kind"] == "reference_confirmed"
    assert latest["configured_sources"] == ["ebay"]
    assert source.calls == 1

    result = run["sources"][0]
    assert (result["read"], result["accepted"], result["recorded"]) == (4, 2, 2)
    # Chaque annonce écartée a son motif : c'est la preuve de l'absence de
    # substitution silencieuse.
    assert result["rejected"] == {"reference_not_stated": 1, "not_a_complete_watch": 1}
    assert {e["code"] for e in result["rejected_examples"]} == set(result["rejected"])
    assert [r["http_status"] for r in result["requests"]] == [200, 200]

    comparables = await _comparables(client, opportunity["id"])
    assert len(comparables) == 2
    assert {c["origin"] for c in comparables} == {"automatic_search"}
    assert all("79230N" not in c["provenance"]["title"] for c in comparables)
    assert all(
        c["price_kind"] == "asking" and c["source_reliability"] == "c"
        for c in comparables
    )

    # Le moteur existant a reçu les comparables : une cote existe, sans clic.
    assert await _count(db_session, "market_valuations", opportunity["id"]) == 1
    assert run["summary"]["recalculation"]["status"] in (
        "recalculated",
        "valuation_only",
    )
    assert run["summary"]["insufficient_data"] is False
    # La nature des prix est dite : ce ne sont pas des ventes.
    assert "pas des ventes" in run["summary"]["price_nature_note"]
    assert run["summary"]["recorded_by_price_kind"] == {"asking": 2}


async def test_no_personal_data_is_stored(
    client: AsyncClient,
    db_session: AsyncSession,
    default_portfolio_id: uuid.UUID,
    install,
) -> None:
    install(FakeSource(ok(EXACT_A, EXACT_B)))
    opportunity = await _opportunity(client, default_portfolio_id, "MS-002")
    rows = (
        await db_session.execute(
            text("select seller_fingerprint, raw_data::text from comparables")
        )
    ).all()
    assert rows and all(fingerprint is None for fingerprint, _ in rows)
    assert all(
        "seller" not in raw.lower().replace("seller_fingerprint", "") for _, raw in rows
    )
    assert opportunity


async def test_one_exact_listing_is_insufficient_and_no_estimate_is_invented(
    client: AsyncClient,
    db_session: AsyncSession,
    default_portfolio_id: uuid.UUID,
    install,
) -> None:
    install(FakeSource(ok(EXACT_A, NEIGHBOUR)))
    opportunity = await _opportunity(client, default_portfolio_id, "MS-003")
    run = (await _latest(client, opportunity["id"]))["run"]

    assert run["summary"]["insufficient_data"] is True
    assert "Données insuffisantes" in run["summary"]["insufficient_data_message"]
    assert run["summary"]["recalculation"]["status"] == "skipped"
    assert await _count(db_session, "market_valuations", opportunity["id"]) == 0


async def test_near_auction_is_recorded_as_current_bid_and_far_one_is_not(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    near = cand(
        "Tudor 79030N Black Bay",
        "3000.00",
        external_id="v1|10|0",
        kind="current_bid",
        ends_in_hours=3,
        bids=5,
    )
    far = cand(
        "Tudor 79030N Black Bay",
        "2000.00",
        external_id="v1|11|0",
        kind="current_bid",
        ends_in_hours=90,
        bids=2,
    )
    install(FakeSource(ok(near, far, EXACT_A)))
    opportunity = await _opportunity(client, default_portfolio_id, "MS-004")

    kinds = {c["price_kind"] for c in await _comparables(client, opportunity["id"])}
    assert kinds == {"current_bid", "asking"}
    run = (await _latest(client, opportunity["id"]))["run"]
    assert run["sources"][0]["rejected"] == {"auction_too_early": 1}
    assert run["summary"]["recorded_by_price_kind"] == {"current_bid": 1, "asking": 1}


# --- Échecs : ne prouvent rien, n'arrêtent pas les autres -------------------


async def test_a_blocked_source_is_diagnosed_and_erases_nothing(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    blocked = SourceOutcome(
        source="ebay",
        status="blocked",
        requests=[RequestRecord("EBAY_FR « Tudor 79030N » (page 1)", 403, 0.3)],
        message=(
            "eBay a refusé l'accès (HTTP 403) : source arrêtée, "
            "aucune nouvelle tentative."
        ),
    )
    install(FakeSource(blocked))
    opportunity = await _opportunity(client, default_portfolio_id, "MS-005")
    run = (await _latest(client, opportunity["id"]))["run"]

    assert run["status"] == "failed"
    source = run["sources"][0]
    assert source["status"] == "blocked"
    assert "HTTP 403" in source["message"]
    assert source["requests"][0]["http_status"] == 403
    assert source["read"] == 0 and source["recorded"] == 0
    assert await _comparables(client, opportunity["id"]) == []


async def test_a_failing_source_does_not_stop_the_others(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    broken = FakeSource(
        SourceOutcome(source="autre", status="error", message="injoignable"),
        name="autre",
    )
    working = FakeSource(ok(EXACT_A, EXACT_B))
    install(broken, working)
    opportunity = await _opportunity(client, default_portfolio_id, "MS-006")
    run = (await _latest(client, opportunity["id"]))["run"]

    assert run["status"] == "partial"
    assert [s["status"] for s in run["sources"]] == ["error", "ok"]
    assert len(await _comparables(client, opportunity["id"])) == 2


async def test_unexpected_crash_is_written_in_the_run_not_raised(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    class Exploding(FakeSource):
        async def search(self, query: SearchQuery) -> SourceOutcome:
            raise RuntimeError("secret interne 12345")

    install(Exploding(ok()))
    opportunity = await _opportunity(client, default_portfolio_id, "MS-007")
    run = (await _latest(client, opportunity["id"]))["run"]
    # Le plantage d'une source est un statut de CETTE source, pas une panne de la
    # recherche : les autres continueraient, et rien de la panne ne fuit.
    assert run["status"] == "failed"
    (source,) = run["sources"]
    assert source["status"] == "error"
    assert "erreur inattendue" in source["message"]
    assert "12345" not in source["message"] + (run["error_message"] or "")


# --- Sobriété : cache, quota, une recherche à la fois ------------------------


async def test_fresh_search_is_reused_and_refresh_too_soon_is_refused(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    source = FakeSource(ok(EXACT_A, EXACT_B))
    install(source)
    opportunity = await _opportunity(client, default_portfolio_id, "MS-008")
    url = f"/api/v1/opportunities/{opportunity['id']}/market-searches"

    again = await client.post(url, json={})
    assert again.status_code == 200
    assert again.json()["reused"] == "fresh" and again.json()["launched"] is False

    forced = await client.post(url, json={"force": True})
    assert forced.status_code == 200
    assert forced.json()["reused"] == "too_soon"
    assert source.calls == 1, "aucune requête n'a été émise pour rien"


async def test_stale_search_is_refreshed_and_known_listings_are_not_duplicated(
    client: AsyncClient,
    db_session: AsyncSession,
    default_portfolio_id: uuid.UUID,
    install,
) -> None:
    source = FakeSource(ok(EXACT_A, EXACT_B))
    install(source)
    opportunity = await _opportunity(client, default_portfolio_id, "MS-009")
    url = f"/api/v1/opportunities/{opportunity['id']}/market-searches"

    await db_session.execute(
        text(
            "update market_search_runs set "
            "created_at = now() - interval '7 hours 2 minutes', "
            "started_at = now() - interval '7 hours 1 minute', "
            "finished_at = now() - interval '7 hours'"
        )
    )
    await db_session.commit()
    latest = await _latest(client, opportunity["id"])
    assert latest["run"]["stale"] is True and latest["run"]["age_minutes"] >= 420

    refreshed = await client.post(url, json={})
    assert refreshed.status_code == 202 and refreshed.json()["launched"] is True
    assert source.calls == 2

    run = (await _latest(client, opportunity["id"]))["run"]
    source_result = run["sources"][0]
    assert (source_result["recorded"], source_result["already_known"]) == (0, 2)
    assert len(await _comparables(client, opportunity["id"])) == 2
    # Rien de nouveau : pas de version de cote de plus dans la chaîne.
    assert run["summary"]["recalculation"] is None


async def test_only_one_search_runs_at_a_time(
    client: AsyncClient,
    db_session: AsyncSession,
    default_portfolio_id: uuid.UUID,
    install,
) -> None:
    source = FakeSource(ok(EXACT_A, EXACT_B))
    install(source)
    opportunity = await _opportunity(client, default_portfolio_id, "MS-010")
    calls_before = source.calls
    await db_session.execute(text("delete from market_search_runs"))
    await db_session.execute(
        text(
            """
            insert into market_search_runs
              (portfolio_id, opportunity_id, reference_id, requested_by_user_id,
               trigger_kind, status, policy_version, started_at)
            select o.portfolio_id, o.id, w.reference_id, u.id,
                   'refresh', 'running', '1.0.0', now()
            from opportunities o join watches w on w.id = o.watch_id, users u
            where o.id = :id limit 1
            """
        ),
        {"id": opportunity["id"]},
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/market-searches", json={}
    )
    assert response.status_code == 200
    assert response.json()["reused"] == "running"
    assert source.calls == calls_before


async def test_interrupted_search_does_not_block_new_ones_forever(
    client: AsyncClient,
    db_session: AsyncSession,
    default_portfolio_id: uuid.UUID,
    install,
) -> None:
    source = FakeSource(ok(EXACT_A, EXACT_B))
    install(source)
    opportunity = await _opportunity(client, default_portfolio_id, "MS-011")
    await db_session.execute(
        text(
            "update market_search_runs set status = 'running', finished_at = null, "
            "started_at = now() - interval '30 minutes'"
        )
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/market-searches",
        json={},
    )
    assert response.status_code == 202
    statuses = (
        await db_session.execute(
            text(
                "select status::text, error_code from market_search_runs "
                "order by created_at"
            )
        )
    ).all()
    assert statuses[0] == ("failed", "STALE_RUN")


async def test_daily_request_guard_skips_the_source(
    client: AsyncClient,
    db_session: AsyncSession,
    default_portfolio_id: uuid.UUID,
    install,
) -> None:
    source = FakeSource(ok(EXACT_A, EXACT_B))
    install(source)
    opportunity = await _opportunity(client, default_portfolio_id, "MS-012")
    await db_session.execute(
        text(
            "update market_search_runs set "
            "started_at = now() - interval '7 hours 1 minute', "
            "finished_at = now() - interval '7 hours', "
            "sources = cast(:sources as jsonb)"
        ),
        {"sources": '[{"source": "ebay", "requests_count": 3995}]'},
    )
    await db_session.commit()

    await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/market-searches", json={}
    )
    run = (await _latest(client, opportunity["id"]))["run"]
    assert run["sources"][0]["status"] == "budget_exhausted"
    assert run["sources"][0]["requests_count"] == 0
    assert source.calls == 1, "seule la première recherche a interrogé la source"


# --- Garde-fous de l'API -------------------------------------------------------


async def test_search_needs_a_configured_source(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    install(FakeSource(ok(), configured=False))
    opportunity = await _opportunity(client, default_portfolio_id, "MS-013")
    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/market-searches", json={}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "COLLECTOR_UNAVAILABLE"
    assert (await _latest(client, opportunity["id"]))["configured_sources"] == []


async def test_search_needs_a_confirmed_reference(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    source = FakeSource(ok(EXACT_A, EXACT_B))
    install(source)
    opportunity = await _opportunity(
        client, default_portfolio_id, "MS-014", confirm=False
    )
    response = await client.post(
        f"/api/v1/opportunities/{opportunity['id']}/market-searches", json={}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REFERENCE_UNCONFIRMED"
    assert source.calls == 0
    assert (await _latest(client, opportunity["id"]))["run"] is None


async def test_unknown_opportunity_is_not_found(client: AsyncClient, install) -> None:
    install(FakeSource(ok()))
    response = await client.get(
        f"/api/v1/opportunities/{uuid.uuid4()}/market-searches/latest"
    )
    assert response.status_code == 404


# --- Plusieurs sources : adjudications, marchands, devises ---------------------


def hammer(
    title: str,
    amount: str,
    currency: str,
    *,
    external_id: str,
    sold_at: datetime,
    source: str = "antiquorum",
    description: str | None = None,
) -> Candidate:
    return Candidate(
        source=source,
        external_id=external_id,
        title=title,
        url=f"https://catalog.example/lots/{external_id}",
        amount=Decimal(amount),
        currency=currency,
        price_kind="hammer",
        observed_at=_now(),
        sold_at=sold_at,
        market_status="sold",
        fees_status="unknown",
        description=description,
        source_country="CH",
    )


LOT_2013 = hammer(
    "Tudor Black Bay 79030N lady's watch 18K gold bracelet",
    "7750",
    "CHF",
    external_id="tudor-79030n-lot-272-285",
    sold_at=datetime(2013, 5, 12, tzinfo=UTC),
)
LOT_2025 = hammer(
    "TUDOR REF. 79030N BLACK BAY, leather strap",
    "75000",
    "HKD",
    external_id="tudor-79030n-lot-378-277",
    sold_at=datetime(2025, 5, 31, tzinfo=UTC),
)
SOLD_OUT = Candidate(
    source="phigora",
    external_id="4554194878521",
    title="Tudor Black Bay 79030N Stainless Steel",
    url="https://shop.example/products/tudor-79030n",
    amount=Decimal("1699"),
    currency="USD",
    price_kind="asking",
    observed_at=_now(),
    market_status="sold",
    source_country="US",
)
MERCHANT = Candidate(
    source="vintage_watch_agency",
    external_id="1448006",
    title="Tudor Black Bay 79030N",
    url="https://shop.example/tudor-79030n-pv-1448006.html",
    amount=Decimal("1520"),
    currency="EUR",
    price_kind="asking",
    observed_at=_now(),
    market_status="active",
    source_country="SE",
)


def named(name: str, *candidates: Candidate, delay: float = 0.0) -> FakeSource:
    import asyncio

    class Slow(FakeSource):
        async def search(self, query: SearchQuery) -> SourceOutcome:
            await asyncio.sleep(delay)
            return await super().search(query)

    outcome = SourceOutcome(source=name, status="ok", candidates=list(candidates))
    return Slow(outcome, name=name)


async def test_auction_results_keep_their_currency_date_and_class_b(
    client: AsyncClient,
    db_session: AsyncSession,
    default_portfolio_id: uuid.UUID,
    install,
) -> None:
    calls: list[set[str]] = []
    install(
        named("antiquorum", LOT_2013, LOT_2025),
        fx_refresh=fx_rates_fake({"CHF": "0.9480", "HKD": "0.1122"}, calls),
    )
    opportunity = await _opportunity(client, default_portfolio_id, "MS-020")

    assert calls == [{"CHF", "HKD"}], "les taux manquants sont demandés, une fois"
    rows = (
        await db_session.execute(
            text(
                """
                select price_kind::text, source_reliability::text, currency,
                       amount_source, amount_eur, rate_to_eur, fx_source,
                       extract(year from observed_at), extract(year from ended_at),
                       market_status::text
                from comparables order by amount_source
                """
            )
        )
    ).all()
    assert len(rows) == 2
    chf = next(r for r in rows if r[2] == "CHF")
    assert chf[0] == "hammer" and chf[1] == "b"  # jamais A : pas une preuve de paiement
    assert chf[3] == Decimal("7750.00") and chf[4] == Decimal("7347.00")
    assert chf[6].startswith("BCE")
    # La date du prix est celle de la vente, pas celle de la lecture : un résultat
    # de 2013 doit peser comme un résultat de 2013.
    assert int(chf[7]) == 2013 and int(chf[8]) == 2013
    assert chf[9] == "sold"

    comparables = await _comparables(client, opportunity["id"])
    provenance = comparables[0]["provenance"]
    assert provenance["fees_status"] == "unknown"
    assert provenance["source_currency"] in ("CHF", "HKD")
    assert provenance["sold_at"]
    assert "commission acheteur" in provenance["price_nature_note"]


async def test_markets_are_grouped_by_nature_never_averaged_together(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    install(
        named("antiquorum", LOT_2013, LOT_2025),
        named("vintage_watch_agency", MERCHANT),
        fx_refresh=fx_rates_fake({"CHF": "0.9480", "HKD": "0.1122"}),
    )
    opportunity = await _opportunity(client, default_portfolio_id, "MS-021")
    groups = (await _latest(client, opportunity["id"]))["run"]["summary"][
        "price_groups"
    ]

    assert set(groups) == {"auction_results", "asking_active"}
    assert groups["auction_results"]["count"] == 2
    assert groups["asking_active"]["count"] == 1
    assert groups["asking_active"]["min_eur"] == "1520.00"
    # Deux fourchettes distinctes : rien n'est mélangé.
    assert groups["auction_results"]["max_eur"] != groups["asking_active"]["max_eur"]


async def test_no_exchange_rate_means_no_comparable_and_the_screen_says_so(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    install(named("antiquorum", LOT_2013), fx_refresh=fx_rates_fake({}))
    opportunity = await _opportunity(client, default_portfolio_id, "MS-022")
    source = (await _latest(client, opportunity["id"]))["run"]["sources"][0]
    assert source["fx_unavailable"] == 1 and source["recorded"] == 0
    assert await _comparables(client, opportunity["id"]) == []


async def test_a_sold_out_undated_price_is_shown_but_kept_out_of_the_estimate(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    install(named("phigora", SOLD_OUT), fx_refresh=fx_rates_fake({"USD": "0.8807"}))
    opportunity = await _opportunity(client, default_portfolio_id, "MS-023")
    source = (await _latest(client, opportunity["id"]))["run"]["sources"][0]
    assert source["rejected"] == {"sold_out_price_undated": 1}
    (info,) = source["informational"]
    assert info["amount"] == "1699" and info["currency"] == "USD"
    assert "non retenu" in info["detail"]
    assert await _comparables(client, opportunity["id"]) == []


async def test_slow_source_does_not_delay_the_others_results(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    install(
        named("sworders", LOT_2013, delay=0.3),
        named("vintage_watch_agency", MERCHANT, delay=0.0),
        fx_refresh=fx_rates_fake({"CHF": "0.9480"}),
    )
    opportunity = await _opportunity(client, default_portfolio_id, "MS-024")
    run = (await _latest(client, opportunity["id"]))["run"]
    # Les sources tournent en parallèle : la plus rapide est consignée la première.
    assert [s["source"] for s in run["sources"]] == ["vintage_watch_agency", "sworders"]
    assert run["status"] == "succeeded"


async def test_configuration_read_from_the_listing_is_kept_not_used(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    install(named("antiquorum", LOT_2013), fx_refresh=fx_rates_fake({"CHF": "0.9480"}))
    opportunity = await _opportunity(client, default_portfolio_id, "MS-025")
    (comparable,) = await _comparables(client, opportunity["id"])
    configuration = comparable["provenance"]["configuration"]
    assert "yellow gold" in " ".join(configuration.get("métal", [])) or "gold" in str(
        configuration
    )
    assert "bracelet métal" in configuration["bracelet"]


async def test_model_is_kept_with_the_reference_and_completes_a_missing_one(
    client: AsyncClient, default_portfolio_id: uuid.UUID, install
) -> None:
    install(named("antiquorum"))

    async def create(ref: str, model: str | None) -> dict[str, object]:
        response = await client.post(
            "/api/v1/opportunities",
            json={
                "portfolio_id": str(default_portfolio_id),
                "source": {"mode": "manual", "manual_identifier": ref},
                "watch": {
                    "brand": "Jaeger-LeCoultre",
                    "reference": "266.1.44",
                    "model": model,
                    "mechanical_condition": "verified",
                    "cosmetic_condition": "excellent",
                    "originality": "original",
                },
                "seller": {"country_code": "FR", "seller_type": "private"},
                "price": {"amount": "3000.00", "currency": "EUR"},
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    first = await create("MODEL-1", None)
    assert first["watch"]["model"] is None
    second = await create("MODEL-2", "Reverso Duetto")
    # Le modèle connu complète la référence partagée...
    assert second["watch"]["model"] == "Reverso Duetto"
    third = await create("MODEL-3", "Autre nom")
    # ...et ne remplace jamais celui qui est déjà renseigné.
    assert third["watch"]["model"] == "Reverso Duetto"
