"""Antiquorum — archives d'adjudications de la maison de Genève.

**Mode d'accès** : pages publiques du catalogue en ligne (`/en/lots?q=…`).
`robots.txt` autorise `/en/lots/` ; il annonce un plan du site qui répond 404 ;
les conditions de vente consultées (Genève) ne mentionnent aucun accès
automatisé. Rythme : au moins 5 s entre deux requêtes (le `crawl-delay` de la
maison pour les robots d'IA).

**Découverte** : la recherche du site est un ET de mots dans le titre et la
description, et **ne retrouve pas un numéro de référence** (« 266.1.44 » donne 0
lot alors que des lots le portent). On cherche donc par marque et modèle, puis on
**filtre la référence exacte** sur la fiche. Sans modèle connu, la marque seule
ramène des centaines de lots : la lecture est alors bornée par le nombre de
pages, et le résultat est déclaré **incomplet**.

**Nature du prix** : « Sold: CHF 7,750 » est un résultat d'adjudication publié.
La page ne dit pas si la commission acheteur y est incluse : `fees_status =
unknown`, jamais normalisé en silence. Le prix affiché dans les données
structurées de la fiche (`schema:price`) est l'**estimation basse**, pas le prix
de vente : il est ignoré.

**Données personnelles / séries** : « Case No. » et « Movement No. » sont des
numéros de série : ils ne sont jamais lus.
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

BASE = "https://catalog.antiquorum.swiss"
SOURCE_NAME = "antiquorum"

_CARD = re.compile(
    r'<div class="shadow mt-4">(.*?)(?=<div class="shadow mt-4">|\Z)', re.S
)
_LOT_NUMBER = re.compile(r"LOT\s+(\d+)")
_AUCTION_LINE = re.compile(r'<div class="ml-auto p-2 bd-highlight">(.*?)</div>', re.S)
_DATE = re.compile(r"([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),\s+(\d{4})")
# Le titre et le texte se lisent dans le bloc **visible** de la fiche : les
# attributs `content="…"` des données structurées se coupent au premier guillemet
# du texte (« Reverso Duetto Joaillerie, ») et perdent la référence.
_NAME = re.compile(r'<p><a href="/en/lots/[^"]*">(.*?)</a></p>', re.S)
_DESCRIPTION_BLOCK = re.compile(
    r'<div class="N_lots_description col">(.*?)</div>', re.S
)
_LINK = re.compile(r'href="(/en/lots/[^"?#]+)')
_SOLD = re.compile(r"Sold:\s*([^<]+)")
_FIELD = re.compile(r"<p><strong>([^<]+)</strong>&emsp;(.*?)</p>", re.S)
_TOTAL = re.compile(r"(\d+)\s+lots")

# Champs conservés. Volontairement une liste blanche : « Case No. » et
# « Movement No. » sont des numéros de série et n'y figurent pas.
_KEPT_FIELDS = {
    "brand",
    "model",
    "reference",
    "year",
    "bracelet",
    "diameter",
    "caliber",
    "signature",
    "accessories",
    "material",
    "dimensions",
}

_PAGE_SIZE = 20

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


def _auction_date(text: str) -> datetime | None:
    match = _DATE.search(text)
    if not match:
        return None
    month = _MONTHS.get(match.group(1)[:3].lower())
    if month is None:
        return None
    return datetime(int(match.group(3)), month, int(match.group(2)), tzinfo=UTC)


def parse_results(
    page_html: str, now: datetime
) -> tuple[list[Candidate], int | None, int]:
    """Lots de la page, nombre total annoncé, nombre de fiches vues.

    Un lot sans « Sold: » (invendu, à venir) n'a pas de prix publié : il est
    ignoré, jamais complété — mais il compte parmi les fiches vues.
    """

    candidates: list[Candidate] = []
    cards = 0
    total_match = _TOTAL.search(re.sub(r"<[^>]+>", " ", page_html))
    total = int(total_match.group(1)) if total_match else None

    for block in _CARD.findall(page_html):
        cards += 1
        link = _LINK.search(block)
        name = _NAME.search(block)
        sold = _SOLD.search(block)
        if not (link and name and sold):
            continue
        amount = parse_amount(html.unescape(sold.group(1)))
        if amount is None:
            continue
        auction = _AUCTION_LINE.search(block)
        sold_at = _auction_date(html.unescape(auction.group(1))) if auction else None

        fields = {}
        for label, value in _FIELD.findall(block):
            key = label.strip().lower()
            if key in _KEPT_FIELDS:
                fields[key] = clean_text(value) or ""
        text_block = _DESCRIPTION_BLOCK.search(block)
        parts = (
            [clean_text(html.unescape(text_block.group(1))) or ""] if text_block else []
        )
        parts += [f"{k}: {v}" for k, v in fields.items() if v]
        description, _ = strip_serials(clean_text(" ".join(parts)) or "")

        slug = link.group(1).rsplit("/", 1)[-1]
        title = clean_text(html.unescape(name.group(1))) or slug
        lot = _LOT_NUMBER.search(re.sub(r"<[^>]+>", " ", block))
        candidates.append(
            Candidate(
                source=SOURCE_NAME,
                external_id=slug,
                title=title,
                url=f"{BASE}{link.group(1)}",
                amount=amount[0],
                currency=amount[1],
                price_kind="hammer",
                observed_at=now,
                ends_at=None,
                sold_at=sold_at,
                market_status="sold",
                fees_status="unknown",
                description=description or None,
                condition_text=None,
                source_country="CH",
                marketplace=f"lot {lot.group(1)}" if lot else None,
            )
        )
    return candidates, total, cards


class AntiquorumSource(HttpSource):
    name = SOURCE_NAME
    min_delay_s = 5.0

    def _words(self, query: SearchQuery) -> str:
        # « Jaeger-LeCoultre » et « Jaeger LeCoultre » donnent les mêmes lots.
        words = [query.brand.replace("-", " ")]
        if query.model:
            words.append(query.model)
        return " ".join(words)

    async def _run(
        self, query: SearchQuery, outcome: SourceOutcome, http: PoliteClient
    ) -> None:
        words = self._words(query)
        for page_number in range(1, self._policy.max_result_pages + 1):
            params: dict[str, str | int] = {"q": words}
            if page_number > 1:
                params["page"] = page_number
            page = await http.get(
                f"{BASE}/en/lots",
                params=params,
                label=f"Antiquorum « {words} » (page {page_number})",
            )
            if page.status != 200:
                outcome.status = "error"
                outcome.message = f"Antiquorum a répondu HTTP {page.status}."
                return
            found, total, cards = parse_results(page.text, datetime.now(UTC))
            outcome.candidates.extend(found)
            if cards == 0 or (total is not None and page_number * _PAGE_SIZE >= total):
                return  # tout a été lu
        # La boucle est allée au bout des pages permises sans avoir tout lu.
        outcome.complete = False
        outcome.message = (
            f"Résultats partiels : {self._policy.max_result_pages} pages lues sur "
            "les résultats de la recherche ; une fiche plus loin n'a pas été vue."
        )
