"""Sworders — résultats d'adjudications d'une maison de ventes britannique.

**Mode d'accès** : pages publiques de l'archive des lots (`/auction/search`).
`robots.txt` n'interdit pas ce chemin et impose un `crawl-delay` de 10 s, respecté.
Les conditions de vente consultées ne mentionnent aucun accès automatisé.

**Découverte** : comme chez Antiquorum, la recherche traite un numéro de référence
comme un numéro de lot (« 266.1.44 » ramène les lots n° 266). On cherche par
marque et modèle. La page de résultats ne donne que le titre du lot : la
**référence figure dans la description**, lue sur la fiche du lot (une requête de
plus, à 10 s d'intervalle) — bornée par `max_detail_pages`, et le résultat est
alors déclaré incomplet si des fiches n'ont pas été lues.

**Nature du prix** : « Sold for £3,500 » est un résultat d'adjudication publié.
Les conditions de vente prévoient une commission acheteur (25 % avant le
1er juillet 2026, 27 % ensuite pour la tranche jusqu'à 20 000 £) mais la page ne
dit pas si le montant affiché l'inclut : `fees_status = unknown`.

**Séries** : la description cite parfois un numéro de série (« serial no. … ») ;
il est retiré avant tout stockage.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime

from app.collection.domain.sanitize import clean_text, strip_serials
from app.market_search.adapters.http_source import HttpSource
from app.market_search.adapters.polite_http import PoliteClient
from app.market_search.domain.candidate import Candidate, SearchQuery, SourceOutcome
from app.market_search.domain.money import parse_amount
from app.market_search.domain.reference import brand_present

BASE = "https://www.sworder.co.uk"
SOURCE_NAME = "sworders"

_CARD = re.compile(
    r'<div class="auction-lot">(.*?)(?=<div class="auction-lot">|\Z)', re.S
)
_LINK = re.compile(r'href="(/auction/lot/[^"]+)"')
_TITLE = re.compile(r"<span class=\'lot-title[^\']*\'>(.*?)</span>\s*</a>", re.S)
_SOLD = re.compile(r"Sold for\s*([^<]+)")
_DETAIL_TITLE = re.compile(r'<h1 class="lot-title[^"]*">(.*?)</h1>', re.S)
_DETAIL_DESC = re.compile(r'<div class="lot-desc">\s*(.*?)\s*</div>', re.S)
_SALE_DATE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+([A-Z][a-z]{2}),\s+(\d{4})\b")
_LOT_ID = re.compile(r"lot=(\d+)")

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ],
        start=1,
    )
}


class LotCard:
    __slots__ = ("lot_id", "path", "title", "price_text")

    def __init__(self, lot_id: str, path: str, title: str, price_text: str) -> None:
        self.lot_id = lot_id
        self.path = path
        self.title = title
        self.price_text = price_text


def parse_results(page_html: str) -> list[LotCard]:
    """Lots vendus de la page de résultats (ceux qui affichent « Sold for »)."""

    cards: list[LotCard] = []
    for block in _CARD.findall(page_html):
        link = _LINK.search(block)
        title = _TITLE.search(block)
        sold = _SOLD.search(block)
        if not (link and title and sold):
            continue
        href = html.unescape(link.group(1))
        lot = _LOT_ID.search(href)
        if lot is None:
            continue
        label = clean_text(re.sub(r"<br\s*/?>", " ", title.group(1))) or ""
        cards.append(
            LotCard(
                lot_id=lot.group(1),
                path=href.split("?", 1)[0],
                title=re.sub(r"^Lot\s+\d+\s*", "", label),
                price_text=html.unescape(sold.group(1)),
            )
        )
    return cards


def _sale_date(text: str) -> datetime | None:
    match = _SALE_DATE.search(text)
    if not match:
        return None
    month = _MONTHS.get(match.group(2).lower())
    if month is None:
        return None
    return datetime(int(match.group(3)), month, int(match.group(1)), tzinfo=UTC)


def parse_lot(page_html: str, card: LotCard, now: datetime) -> Candidate | None:
    """Fiche d'un lot vendu → candidat. `None` si le prix n'est pas lisible."""

    price = parse_amount(card.price_text)
    if price is None:
        return None
    title = _DETAIL_TITLE.search(page_html)
    description = _DETAIL_DESC.search(page_html)
    text = re.sub(r"<[^>]+>", " ", page_html)
    clean_title = clean_text(html.unescape(title.group(1))) if title else card.title
    body, _ = (
        strip_serials(clean_text(description.group(1)) or "")
        if description
        else ("", False)
    )
    return Candidate(
        source=SOURCE_NAME,
        external_id=card.lot_id,
        title=clean_title or card.title,
        url=f"{BASE}{card.path}?lot={card.lot_id}",
        amount=price[0],
        currency=price[1],
        price_kind="hammer",
        observed_at=now,
        sold_at=_sale_date(html.unescape(text)),
        market_status="sold",
        fees_status="unknown",
        description=body or None,
        source_country="GB",
    )


class SwordersSource(HttpSource):
    name = SOURCE_NAME
    min_delay_s = 10.0

    async def _run(
        self, query: SearchQuery, outcome: SourceOutcome, http: PoliteClient
    ) -> None:
        words = " ".join(w for w in (query.brand.replace("-", " "), query.model) if w)
        cards: list[LotCard] = []
        for page_number in range(1, self._policy.max_result_pages + 1):
            page = await http.get(
                f"{BASE}/auction/search",
                params={"sd": 2, "st": words, "sto": 0, "pp": 96, "pn": page_number},
                label=f"Sworders « {words} » (page {page_number})",
            )
            if page.status != 200:
                outcome.status = "error"
                outcome.message = f"Sworders a répondu HTTP {page.status}."
                return
            found = parse_results(page.text)
            cards.extend(found)
            if len(found) < 96:
                break
        else:
            outcome.complete = False

        # Seules les fiches dont le titre porte la marque sont lues : la
        # référence est dans la description, qui n'est que sur la fiche.
        candidates_cards = [c for c in cards if brand_present(c.title, query.brand)]
        to_read = candidates_cards[: self._policy.max_detail_pages]
        if len(candidates_cards) > len(to_read):
            outcome.complete = False
            outcome.message = (
                f"Résultats partiels : {len(to_read)} fiches lues sur "
                f"{len(candidates_cards)} lots de la marque."
            )

        now = datetime.now(UTC)
        for card in to_read:
            page = await http.get(
                f"{BASE}{card.path}",
                params={"lot": card.lot_id},
                label=f"Sworders lot {card.lot_id}",
            )
            if page.status != 200:
                continue
            candidate = parse_lot(page.text, card, now)
            if candidate is not None:
                outcome.candidates.append(candidate)
