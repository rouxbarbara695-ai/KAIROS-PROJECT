"""Taux de change de référence de la Banque centrale européenne.

Publiés chaque jour ouvré, gratuits et sans inscription : c'est la source de
taux de la recherche autonome, dont les sources publient dans **leur** devise
(livres, francs suisses, dollars de Hong Kong…).

Ce que le taux enregistré dit (CLAUDE.md règle 3) : la devise source, le sens
(1 unité de devise → EUR), la valeur, la source (« BCE » et la date de
référence de la BCE) et l'instant où KAIROS l'a relevé. Aucun taux inventé : si
la BCE ne répond pas, ou ne publie pas la devise, aucun comparable n'est
enregistré dans cette devise, et l'écran le dit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from xml.etree import ElementTree

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.collection.adapters.http_fetcher import USER_AGENT
from app.shared.infrastructure.db.models.reference_data import FxRate

logger = structlog.get_logger()

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
_NS = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}


def parse_ecb_rates(xml_text: str) -> tuple[str, dict[str, Decimal]]:
    """`(date de référence, {devise: unités de devise pour 1 EUR})`."""

    root = ElementTree.fromstring(xml_text)  # noqa: S314 — flux public de la BCE, HTTPS
    day = root.find(".//e:Cube[@time]", _NS)
    if day is None:
        raise ValueError("Flux de la BCE sans date de référence.")
    rates = {
        cube.attrib["currency"]: Decimal(cube.attrib["rate"])
        for cube in day.findall("e:Cube", _NS)
    }
    return day.attrib["time"], rates


async def refresh_ecb_rates(
    session: AsyncSession,
    currencies: set[str],
    *,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Enregistre les taux demandés. Rend le nombre de taux ajoutés."""

    owned = client is None
    client = client or httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15)
    try:
        response = await client.get(ECB_DAILY_URL)
        if response.status_code != 200:
            logger.warning("ecb_unavailable", status=response.status_code)
            return 0
        day, rates = parse_ecb_rates(response.text)
    except (httpx.HTTPError, ValueError, ElementTree.ParseError) as error:
        logger.warning("ecb_failed", error_type=type(error).__name__)
        return 0
    finally:
        if owned:
            await client.aclose()

    now = datetime.now(UTC)
    added = 0
    for currency in sorted(currencies):
        per_euro = rates.get(currency)
        if per_euro is None or per_euro <= 0:
            continue
        session.add(
            FxRate(
                base_currency=currency,
                quote_currency="EUR",
                # La BCE publie « unités de devise pour 1 EUR » ; KAIROS stocke
                # « EUR pour 1 unité de devise » : l'inverse.
                rate=(Decimal(1) / per_euro).quantize(Decimal("0.000000000001")),
                observed_at=now,
                source_name=f"BCE (référence du {day})",
            )
        )
        added += 1
    await session.commit()
    return added
