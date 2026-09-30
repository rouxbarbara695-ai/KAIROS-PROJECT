"""Vintage Watch Agency — marchand européen (prix demandés en euros).

**Mode d'accès** : pages publiques. `robots.txt` n'exclut que `/reviews.html`
pour les agents génériques. Sa page de conditions d'utilisation ne rend aucun
texte à un client sans navigateur : **le contenu des conditions n'a pas pu être
lu**, ce qui est consigné au registre — un robots.txt permissif n'est pas une
autorisation contractuelle.

**Découverte** : la recherche du site (`/search-results.html?keyword=…`) retrouve
une référence par son numéro. Les cartes de résultats portent la référence ; la
fiche produit, lue seulement pour les cartes qui correspondent, confirme la
disponibilité et l'état.

**Nature du prix** : prix demandé d'un marchand, en stock. Ce n'est ni une vente
ni un prix réalisé. La fiche précise parfois utiliser une **image d'illustration** :
la description est une déclaration du marchand, pas une preuve de l'exemplaire.
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
from app.market_search.domain.reference import match_reference

BASE = "https://www.vintagewatchagency.com"
SOURCE_NAME = "vintage_watch_agency"

_CARD = re.compile(
    r"<div id='p_i_(\d+)'[^>]*>\s*<a href='([^']*-pv-\d+\.html)'(.*?)</a>", re.S
)
_MODEL = re.compile(r"prod-list-item-details-model'>(.*?)</span>", re.S)
_NAME = re.compile(r"prod-list-item-details-name'>(.*?)</span>", re.S)
_INFO = re.compile(r"prod-details-info'>(.*?)</span>\s*<span class='prod-list", re.S)
_PRICE = re.compile(r"normalPrice[^']*'>(.*?)</span>", re.S)
_ROW = re.compile(r"<tr[^>]*><td>([^<]+)</td><td[^>]*>(.*?)</td></tr>", re.S)
_STOCK = re.compile(r"On stock|In stock", re.I)
_UNAVAILABLE = re.compile(r"Sold out|Out of stock|Sold\b|Reserved", re.I)

# Champs de la fiche repris (liste blanche).
_KEPT = {
    "year",
    "condition",
    "original warranty",
    "box",
    "model",
    "manufacturer",
    "series",
    "type",
    "diameter",
    "case",
    "bracelet",
    "dial",
    "movement type",
}


class Card:
    __slots__ = ("product_id", "path", "model", "name", "info", "price")

    def __init__(
        self, product_id: str, path: str, model: str, name: str, info: str, price: str
    ) -> None:
        self.product_id = product_id
        self.path = path
        self.model = model
        self.name = name
        self.info = info
        self.price = price

    @property
    def text(self) -> str:
        return f"{self.model} {self.name} {self.info}"


def _text(raw: str | None) -> str:
    return clean_text(html.unescape(raw or "")) or ""


def parse_results(page_html: str) -> list[Card]:
    cards: list[Card] = []
    for product_id, path, body in _CARD.findall(page_html):
        model = _MODEL.search(body)
        name = _NAME.search(body)
        price = _PRICE.search(body)
        info = _INFO.search(body)
        if not (name and price):
            continue
        cards.append(
            Card(
                product_id,
                path,
                _text(model.group(1) if model else ""),
                _text(name.group(1)),
                _text(info.group(1) if info else ""),
                _text(price.group(1)),
            )
        )
    return cards


def parse_detail(page_html: str) -> tuple[dict[str, str], str]:
    """Champs de la fiche (liste blanche) et disponibilité déclarée."""

    fields: dict[str, str] = {}
    for label, value in _ROW.findall(page_html):
        key = _text(label).rstrip(":").lower()
        if key in _KEPT:
            fields[key] = _text(value)
    if _STOCK.search(page_html):
        status = "active"
    elif _UNAVAILABLE.search(re.sub(r"<[^>]+>", " ", page_html)[:20000]):
        status = "sold"
    else:
        status = "unknown"
    return fields, status


class VintageWatchAgencySource(HttpSource):
    name = SOURCE_NAME
    min_delay_s = 3.0

    async def _run(
        self, query: SearchQuery, outcome: SourceOutcome, http: PoliteClient
    ) -> None:
        page = await http.get(
            f"{BASE}/search-results.html",
            params={"keyword": query.reference},
            label=f"Vintage Watch Agency « {query.reference} »",
        )
        if page.status != 200:
            outcome.status = "error"
            outcome.message = f"Vintage Watch Agency a répondu HTTP {page.status}."
            return
        cards = [
            c
            for c in parse_results(page.text)
            if match_reference(c.text, query.reference).found
        ]
        now = datetime.now(UTC)
        for card in cards[: self._policy.max_detail_pages]:
            price = parse_amount(card.price, default_currency="EUR")
            if price is None:
                continue
            detail = await http.get(
                f"{BASE}/{card.path.lstrip('/')}",
                label=f"Vintage Watch Agency fiche {card.product_id}",
            )
            fields, status = (
                parse_detail(detail.text) if detail.status == 200 else ({}, "unknown")
            )
            description, _ = strip_serials(
                " ".join(
                    [card.model, card.info, *[f"{k}: {v}" for k, v in fields.items()]]
                )
            )
            outcome.candidates.append(
                Candidate(
                    source=SOURCE_NAME,
                    external_id=card.product_id,
                    title=card.name,
                    url=f"{BASE}/{card.path.lstrip('/')}",
                    amount=price[0],
                    currency=price[1],
                    price_kind="asking",
                    observed_at=now,
                    market_status=status,  # type: ignore[arg-type]
                    condition_text=fields.get("condition"),
                    description=description or None,
                    source_country="SE",
                )
            )
