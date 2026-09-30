"""Catalogue d'un marchand par le protocole UCP (Universal Commerce Protocol).

**Mode d'accès** : le marchand **publie lui-même** ce canal pour les agents. Son
profil `/.well-known/ucp` déclare les capacités `dev.ucp.shopping.catalog.search`
et `…lookup` et l'adresse d'un serveur MCP ; le protocole prévoit une
« intégration sans inscription préalable » de toute plateforme qui publie son
propre profil. KAIROS publie le sien (`docs/ucp/kairos-agent-profile.json`) et le
joint à chaque requête (`meta.ucp-agent.profile`). Il **ne déclare que la lecture
de catalogue** : ni panier, ni commande, ni paiement.

Limites à ne pas perdre de vue :

- c'est un canal de recherche de produits, **pas une licence** de constitution
  d'une base de marché : KAIROS interroge à la demande et ne conserve que les
  observations qu'il utilise, avec leur provenance ;
- les conditions d'utilisation de la boutique n'ont pas pu être lues depuis
  l'environnement de développement (page protégée par un défi anti-robot) : le
  registre le consigne ;
- les prix sont ceux du marchand, dans **sa devise** (unités mineures) ;
- un produit « Sold » ou épuisé garde son ancien prix affiché : c'est **le
  dernier prix demandé**, pas un prix de vente.

Les étiquettes (`tags`) du catalogue peuvent contenir un numéro de série : elles
ne sont jamais lues.
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.collection.domain.sanitize import clean_text, strip_serials
from app.market_search.adapters.http_source import HttpSource
from app.market_search.adapters.polite_http import PoliteClient, SourceStop
from app.market_search.domain.candidate import Candidate, SearchQuery, SourceOutcome
from app.market_search.domain.policy import SearchPolicy

# Profil d'agent de KAIROS. Servi en `application/json` par jsDelivr depuis le
# dépôt public, faute d'un domaine qui le publie ; à remplacer par l'adresse du
# domaine de production quand elle le servira (Q-04).
KAIROS_UCP_PROFILE_URL = (
    "https://cdn.jsdelivr.net/gh/rouxbarbara695-ai/KAIROS-PROJECT"
    "@claude/kairos-multisource-discovery/docs/ucp/kairos-agent-profile.json"
)
CATALOG_SEARCH = "dev.ucp.shopping.catalog.search"

_ZERO_DECIMAL = {"JPY", "KRW", "VND", "CLP"}
_SOLD_TAGS = re.compile(r"availability\|sold|mark as sold", re.I)


def _major_units(amount: int, currency: str) -> Decimal:
    if currency in _ZERO_DECIMAL:
        return Decimal(amount)
    return Decimal(amount) / Decimal(100)


def parse_product(
    product: dict[str, Any], *, source: str, country: str, now: datetime
) -> Candidate | None:
    title = product.get("title")
    url = product.get("url")
    price_range = product.get("price_range")
    if not isinstance(title, str) or not isinstance(url, str):
        return None
    if not isinstance(price_range, dict):
        return None
    low = price_range.get("min")
    if not isinstance(low, dict):
        return None
    amount, currency = low.get("amount"), low.get("currency")
    if not isinstance(amount, int) or not isinstance(currency, str):
        return None
    if amount <= 0 or len(currency) != 3:
        return None

    variants = [v for v in product.get("variants", []) if isinstance(v, dict)]
    availability = [
        v.get("availability", {}).get("available")
        for v in variants
        if isinstance(v.get("availability"), dict)
    ]
    tags = [t for t in product.get("tags", []) if isinstance(t, str)]
    marked_sold = any(_SOLD_TAGS.search(t) for t in tags)
    if marked_sold or (availability and not any(availability)):
        status = "sold"
    elif availability and any(availability):
        status = "active"
    else:
        status = "unknown"

    description_block = product.get("description")
    raw_description = (
        description_block.get("html") if isinstance(description_block, dict) else None
    )
    description, _ = strip_serials(
        clean_text(html.unescape(str(raw_description or ""))) or ""
    )

    external = str(product.get("id") or product.get("handle") or url)
    return Candidate(
        source=source,
        external_id=external.rsplit("/", 1)[-1],
        title=clean_text(title) or title,
        url=url.split("?", 1)[0],
        amount=_major_units(amount, currency),
        currency=currency.upper(),
        price_kind="asking",
        observed_at=now,
        market_status=status,  # type: ignore[arg-type]
        description=description or None,
        source_country=country,
    )


class UcpCatalogSource(HttpSource):
    def __init__(
        self,
        client: httpx.AsyncClient,
        policy: SearchPolicy,
        *,
        name: str,
        site: str,
        country: str,
        profile_url: str = KAIROS_UCP_PROFILE_URL,
        **kwargs: object,
    ) -> None:
        super().__init__(client, policy, **kwargs)
        self.name = name
        self._site = site.rstrip("/")
        self._country = country
        self._profile_url = profile_url

    min_delay_s = 1.0

    async def _run(
        self, query: SearchQuery, outcome: SourceOutcome, http: PoliteClient
    ) -> None:
        # 1. Le profil du marchand dit où est le serveur et ce qu'il sait faire.
        profile_page = await http.get(
            f"{self._site}/.well-known/ucp",
            label=f"Profil UCP de {self._site}",
            robots=False,
        )
        if profile_page.status != 200:
            outcome.status = "error"
            outcome.message = (
                f"Profil UCP de {self._site} indisponible (HTTP {profile_page.status})."
            )
            return
        try:
            profile = json.loads(profile_page.text)["ucp"]
            capabilities = profile["capabilities"]
            endpoint = next(
                service["endpoint"]
                for service in profile["services"]["dev.ucp.shopping"]
                if service.get("transport") == "mcp" and service.get("endpoint")
            )
        except (KeyError, StopIteration, ValueError, TypeError):
            raise SourceStop(
                "error", f"Profil UCP de {self._site} illisible ou sans serveur MCP."
            ) from None
        if CATALOG_SEARCH not in capabilities:
            raise SourceStop(
                "blocked",
                f"{self._site} ne déclare pas la recherche de catalogue "
                f"({CATALOG_SEARCH}) : source non utilisable.",
            )
        if not str(endpoint).startswith("https://"):
            raise SourceStop("error", "Serveur MCP du profil UCP hors HTTPS : refusé.")

        # 2. Recherche par texte libre : marque, modèle si connu, référence.
        words = " ".join(w for w in (query.brand, query.model, query.reference) if w)
        cursor: str | None = None
        now = datetime.now(UTC)
        for page_number in range(1, self._policy.max_result_pages + 1):
            pagination: dict[str, object] = {"limit": 25}
            if cursor:
                pagination["cursor"] = cursor
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": page_number,
                "params": {
                    "name": "search_catalog",
                    "arguments": {
                        "meta": {"ucp-agent": {"profile": self._profile_url}},
                        "catalog": {
                            "query": words,
                            "context": {"address_country": "FR"},
                            "pagination": pagination,
                        },
                    },
                },
            }
            response = await http.post_json(
                str(endpoint),
                payload,
                label=f"UCP search_catalog « {words} » (page {page_number})",
            )
            try:
                body = json.loads(response.text)
            except ValueError:
                raise SourceStop("error", "Réponse UCP illisible.") from None
            if "error" in body:
                detail = (
                    body["error"].get("data", {})
                    if isinstance(body["error"], dict)
                    else {}
                )
                raise SourceStop(
                    "error",
                    "Le serveur UCP a refusé la requête : "
                    f"{detail.get('code', 'erreur')} — "
                    f"{str(detail.get('content', ''))[:120]}",
                )
            content = body.get("result", {}).get("structuredContent", {})
            for product in content.get("products", []):
                if isinstance(product, dict):
                    parsed = parse_product(
                        product, source=self.name, country=self._country, now=now
                    )
                    if parsed is not None:
                        outcome.candidates.append(parsed)
            paging = content.get("pagination", {})
            if not paging.get("has_next_page"):
                return
            cursor = paging.get("cursor")
        outcome.complete = False
        outcome.message = (
            f"Résultats partiels : {self._policy.max_result_pages} pages lues ; "
            "le catalogue en contient davantage."
        )
