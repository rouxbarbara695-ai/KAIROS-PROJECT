"""Preuve d'accès réel : interroge eBay avec de vrais identifiants.

Usage :
    python -m app.market_search.probe                 # les trois références de l'essai
    python -m app.market_search.probe "Omega|1561.61.00" "Cartier|W1002253"
    python -m app.market_search.probe --json preuve.json

Ce que fait cette commande, et rien d'autre : elle lance la **vraie** recherche
(requêtes réelles, aucun simulacre), applique le **vrai** contrôle d'identité, et
imprime pour chaque référence les sources interrogées, les requêtes émises et
leur statut HTTP, les annonces lues, retenues et écartées avec leur motif, et le
temps total. Elle n'écrit rien en base et ne touche à aucun comparable.

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
from typing import Any

from app.market_search.application.runtime import default_sources
from app.market_search.domain.candidate import SearchQuery
from app.market_search.domain.dedupe import deduplicate
from app.market_search.domain.policy import SearchPolicy
from app.market_search.domain.screening import screen
from app.shared.config import get_settings

DEFAULT_REFERENCES = [
    "Jaeger-LeCoultre|266.1.44",
    "Cartier|W1002253",
    "Omega|1561.61.00",
]


async def probe_reference(brand: str, reference: str) -> dict[str, Any]:
    settings = get_settings()
    policy = SearchPolicy()
    started = time.monotonic()
    report: dict[str, Any] = {
        "brand": brand,
        "reference": reference,
        "started_at": datetime.now(UTC).isoformat(),
        "sources": [],
    }
    async with default_sources(settings, policy) as sources:
        for source in sources:
            outcome = await source.search(SearchQuery(brand=brand, reference=reference))
            verdicts = [
                (
                    candidate,
                    screen(
                        candidate,
                        brand=brand,
                        reference=reference,
                        model=None,
                        policy=policy,
                    ),
                )
                for candidate in outcome.candidates
            ]
            accepted = [c for c, v in verdicts if v.accepted]
            deduped = deduplicate(accepted)
            rejected = Counter(v.code for _, v in verdicts if not v.accepted)
            report["sources"].append(
                {
                    "source": source.name,
                    "status": outcome.status,
                    "message": outcome.message,
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
                    "accepted_before_dedupe": len(accepted),
                    "duplicates": len(deduped.duplicates),
                    "usable": [
                        {
                            "title": c.title,
                            "url": c.url,
                            "amount": str(c.amount),
                            "currency": c.currency,
                            "price_kind": c.price_kind,
                            "marketplace": c.marketplace,
                            "country": c.country,
                        }
                        for c in deduped.kept
                    ],
                    "rejected": dict(rejected),
                    "rejected_examples": [
                        {"title": c.title[:120], "code": v.code}
                        for c, v in verdicts
                        if not v.accepted
                    ][:6],
                }
            )
    report["total_s"] = round(time.monotonic() - started, 1)
    return report


def render(report: dict[str, Any]) -> str:
    lines = [
        f"\n=== {report['brand']} {report['reference']} — {report['total_s']} s ==="
    ]
    for source in report["sources"]:
        lines.append(f"  source : {source['source']} — {source['status']}")
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
            f"(doublons fusionnés {source['duplicates']}) · "
            f"écartées {dict(source['rejected'])}"
        )
        for item in source["usable"]:
            lines.append(
                f"      ✔ {item['amount']} {item['currency']} [{item['price_kind']}] "
                f"{item['title'][:80]} — {item['url']}"
            )
        for example in source["rejected_examples"]:
            lines.append(f"      ✘ {example['code']}: {example['title']}")
    return "\n".join(lines)


async def main(arguments: list[str]) -> int:
    output: str | None = None
    if "--json" in arguments:
        index = arguments.index("--json")
        output = arguments[index + 1]
        del arguments[index : index + 2]

    references = arguments or DEFAULT_REFERENCES
    settings = get_settings()
    if not (settings.ebay_client_id and settings.ebay_client_secret):
        print(
            "Aucun identifiant eBay : définir EBAY_CLIENT_ID et EBAY_CLIENT_SECRET.\n"
            "Aucune requête n'a été émise ; il n'y a donc rien à prouver.",
            file=sys.stderr,
        )
        return 2

    reports = []
    for spec in references:
        brand, _, reference = spec.partition("|")
        if not reference:
            print(f"Référence mal formée (attendu « Marque|Référence ») : {spec}")
            return 2
        report = await probe_reference(brand.strip(), reference.strip())
        reports.append(report)
        print(render(report))

    if output:
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(reports, handle, ensure_ascii=False, indent=2)
        print(f"\nRapport écrit : {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
