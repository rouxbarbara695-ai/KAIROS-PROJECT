"""Preuve d'accès réel : interroge les sources avec de vraies requêtes.

Usage :
    python -m app.market_search.probe        # trois références pilotes + une nouvelle
    python -m app.market_search.probe "Omega|1561.61.00|Constellation"
    python -m app.market_search.probe --sources antiquorum,sworders --json preuve.json

Une référence s'écrit « Marque|Référence » ou « Marque|Référence|Modèle ». Le
modèle sert aux sources dont la recherche ne retrouve pas un numéro de
référence (maisons de ventes) : sans lui, elles cherchent la marque seule et
lisent peu de pages.

Ce que fait cette commande, et rien d'autre : elle lance la **vraie** recherche
(requêtes réelles, aucun simulacre), applique le **vrai** contrôle d'identité, et
imprime pour chaque référence et chaque source : les requêtes émises et leur
statut HTTP, les annonces lues, retenues et écartées avec leur motif, la nature
de chaque prix, et le temps total. Elle n'écrit rien en base.

C'est la seule preuve que l'accès fonctionne : un test avec une source simulée
ne prouve pas l'accès réel.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.collection.adapters.http_fetcher import USER_AGENT
from app.market_search.application.runtime import default_sources
from app.market_search.domain.candidate import Candidate, SearchQuery, SourceOutcome
from app.market_search.domain.dedupe import deduplicate
from app.market_search.domain.policy import SearchPolicy
from app.market_search.domain.screening import screen
from app.shared.config import get_settings
from app.shared.infrastructure.fx_ecb import ECB_DAILY_URL, parse_ecb_rates

DEFAULT_REFERENCES = [
    "Jaeger-LeCoultre|266.1.44|Reverso Duetto",
    "Cartier|W1002253|Must de Cartier Vendome",
    "Omega|1561.61.00|Constellation",
    "Omega|3570.50.00|Speedmaster",  # référence nouvelle : rien n'y est réglé à la main
]


async def _ecb() -> dict[str, Decimal]:
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=15
        ) as client:
            response = await client.get(ECB_DAILY_URL)
            return parse_ecb_rates(response.text)[1]
    except Exception:  # noqa: BLE001 — la conversion n'est qu'un confort d'affichage
        return {}


def _eur(candidate: Candidate, rates: dict[str, Decimal]) -> str:
    if candidate.currency == "EUR":
        return f"{candidate.amount:.0f} €"
    per_euro = rates.get(candidate.currency)
    if not per_euro:
        return "taux BCE indisponible"
    return f"≈ {candidate.amount / per_euro:.0f} € (BCE, indicatif)"


async def probe_reference(
    brand: str, reference: str, model: str | None, sources_override: str | None
) -> dict[str, Any]:
    settings = get_settings()
    if sources_override:
        settings = settings.model_copy(
            update={"market_search_sources": sources_override}
        )
    policy = SearchPolicy()
    query = SearchQuery(brand=brand, reference=reference, model=model)
    rates = await _ecb()
    started = time.monotonic()
    report: dict[str, Any] = {
        "brand": brand,
        "reference": reference,
        "model": model,
        "started_at": datetime.now(UTC).isoformat(),
        "sources": [],
    }

    async with default_sources(settings, policy) as sources:
        active = [s for s in sources if s.is_configured()]
        skipped = [s.name for s in sources if not s.is_configured()]

        async def run(source: Any) -> tuple[str, SourceOutcome, float]:
            t0 = time.monotonic()
            return source.name, await source.search(query), time.monotonic() - t0

        results = await asyncio.gather(*(run(s) for s in active))

    for name, outcome, seconds in results:
        verdicts = [
            (c, screen(c, brand=brand, reference=reference, model=model, policy=policy))
            for c in outcome.candidates
        ]
        accepted = [c for c, v in verdicts if v.accepted]
        deduped = deduplicate(accepted)
        rejected = Counter(v.code for _, v in verdicts if not v.accepted)
        report["sources"].append(
            {
                "source": name,
                "status": outcome.status,
                "complete": outcome.complete,
                "message": outcome.message,
                "seconds": round(seconds, 1),
                "requests": [
                    {
                        "label": r.label,
                        "http_status": r.http_status,
                        "elapsed_s": r.elapsed_s,
                        "note": r.note,
                    }
                    for r in outcome.requests
                ],
                "read": len(outcome.candidates),
                "duplicates": len(deduped.duplicates),
                "usable": [
                    {
                        "title": c.title,
                        "url": c.url,
                        "amount": str(c.amount),
                        "currency": c.currency,
                        "eur": _eur(c, rates),
                        "price_kind": c.price_kind,
                        "market_status": c.market_status,
                        "sold_at": c.sold_at.date().isoformat() if c.sold_at else None,
                        "fees_status": c.fees_status,
                        "country": c.source_country,
                    }
                    for c in deduped.kept
                ],
                "rejected": dict(rejected),
                "rejected_examples": [
                    {"title": c.title[:100], "code": v.code}
                    for c, v in verdicts
                    if not v.accepted and v.code != "reference_not_stated"
                ][:4],
            }
        )
    report["not_configured"] = skipped
    report["total_s"] = round(time.monotonic() - started, 1)
    return report


def render(report: dict[str, Any]) -> str:
    title = f"{report['brand']} {report['reference']}"
    if report["model"]:
        title += f" ({report['model']})"
    lines = [f"\n=== {title} — {report['total_s']} s ==="]
    for source in report["sources"]:
        partial = "" if source["complete"] else " · INCOMPLET"
        lines.append(
            f"  source : {source['source']} — {source['status']}{partial} "
            f"({source['seconds']} s)"
        )
        if source["message"]:
            lines.append(f"    diagnostic : {source['message']}")
        for request in source["requests"]:
            note = f" ({request['note']})" if request["note"] else ""
            lines.append(
                f"    requête : {request['label']} → HTTP {request['http_status']} "
                f"en {request['elapsed_s']} s{note}"
            )
        lines.append(
            f"    lues {source['read']} · retenues {len(source['usable'])} "
            f"(doublons {source['duplicates']}) · écartées {source['rejected']}"
        )
        for item in source["usable"]:
            sold = f" le {item['sold_at']}" if item["sold_at"] else ""
            lines.append(
                f"      ✔ {item['amount']} {item['currency']} {item['eur']} "
                f"[{item['price_kind']}/{item['market_status']}{sold}, "
                f"frais {item['fees_status']}] {item['title'][:70]} — {item['url']}"
            )
        for example in source["rejected_examples"]:
            lines.append(f"      ✘ {example['code']}: {example['title']}")
    if report["not_configured"]:
        lines.append(
            "  non configurées (aucune requête) : "
            + ", ".join(report["not_configured"])
        )
    return "\n".join(lines)


async def main(arguments: list[str]) -> int:
    output: str | None = None
    sources_override: str | None = None
    if "--json" in arguments:
        index = arguments.index("--json")
        output = arguments[index + 1]
        del arguments[index : index + 2]
    if "--sources" in arguments:
        index = arguments.index("--sources")
        sources_override = arguments[index + 1]
        del arguments[index : index + 2]

    references = arguments or DEFAULT_REFERENCES
    reports = []
    for spec in references:
        brand, _, rest = spec.partition("|")
        reference, _, model = rest.partition("|")
        if not reference:
            print(
                f"Référence mal formée (attendu « Marque|Référence[|Modèle] ») : {spec}"
            )
            return 2
        report = await probe_reference(
            brand.strip(), reference.strip(), model.strip() or None, sources_override
        )
        reports.append(report)
        print(render(report), flush=True)

    if output:
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(reports, handle, ensure_ascii=False, indent=2)
        print(f"\nRapport écrit : {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
