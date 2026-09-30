"""Source eBay par son API officielle « Browse » — jamais par les pages du site.

C'est un accès **autorisé** : programme développeur gratuit d'eBay, jeton OAuth
« client credentials », quota publié (5 000 appels par jour). Les pages du site
restent interdites au collecteur (`access_policy.py`) : ce sont deux modes
d'accès distincts, avec des conditions distinctes.

Obligations du contrat de licence de l'API prises en compte ici :
- aucune donnée personnelle conservée : ni pseudonyme de vendeur, ni note ;
- aucune information sur les réserves d'enchères ;
- l'âge d'une annonce affichée est rendu visible (`observed_at`) ;
- aucune statistique de catégorie ou de site : on ne publie que des annonces
  correspondant à une référence précise.

Ce que l'API ne donne pas : les ventes conclues (l'API Marketplace Insights est
réservée à des partenaires agréés). Tout ce qui vient d'ici est donc un **prix
demandé** ou une **enchère en cours** — jamais un prix réalisé.

Règle d'arrêt : au premier refus explicite (401, 403, 429) la source s'arrête,
sans nouvelle tentative. Une erreur de réseau ou un 5xx n'arrête que la
requête concernée.
"""

from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

import httpx
import structlog

from app.market_search.domain.candidate import (
    Candidate,
    RequestRecord,
    SearchQuery,
    SourceOutcome,
)
from app.market_search.domain.policy import SearchPolicy
from app.market_search.domain.reference import spelling_variants

logger = structlog.get_logger()

SOURCE_NAME = "ebay"
_SCOPE = "https://api.ebay.com/oauth/api_scope"
_BASE_URLS = {
    "production": "https://api.ebay.com",
    "sandbox": "https://api.sandbox.ebay.com",
}
_PAGE_LIMIT_MAX = 200  # plafond de l'API


def _decimal(value: object) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clean_url(raw: object, legacy_id: object) -> str | None:
    """Adresse de l'annonce, sans paramètres de suivi."""

    if isinstance(raw, str):
        parts = urlsplit(raw)
        if parts.scheme == "https" and ".ebay." in f".{parts.netloc}":
            return f"https://{parts.netloc}{parts.path}"
    if legacy_id:
        return f"https://www.ebay.com/itm/{legacy_id}"
    return None


def parse_item(
    item: dict[str, Any], marketplace: str, now: datetime
) -> Candidate | None:
    """Une annonce de l'API en candidat ; `None` si elle est inexploitable.

    Un champ absent ne se devine pas : sans identifiant, prix ou devise lisibles,
    l'annonce est ignorée plutôt que complétée.
    """

    external_id = item.get("itemId")
    title = item.get("title")
    if not isinstance(external_id, str) or not isinstance(title, str):
        return None

    options = [o for o in item.get("buyingOptions", []) if isinstance(o, str)]
    is_auction = "AUCTION" in options
    price_block = (
        item.get("currentBidPrice") or item.get("price")
        if is_auction
        else item.get("price")
    )
    if not isinstance(price_block, dict):
        return None
    amount = _decimal(price_block.get("value"))
    currency = price_block.get("currency")
    if amount is None or not isinstance(currency, str) or len(currency) != 3:
        return None

    url = _clean_url(item.get("itemWebUrl"), item.get("legacyItemId"))
    if url is None:
        return None

    shipping_amount: Decimal | None = None
    shipping_currency: str | None = None
    fixed = []
    for option in item.get("shippingOptions", []) or []:
        cost = option.get("shippingCost") if isinstance(option, dict) else None
        if (
            isinstance(option, dict)
            and option.get("shippingCostType") == "FIXED"
            and isinstance(cost, dict)
            and _decimal(cost.get("value")) is not None
            and isinstance(cost.get("currency"), str)
        ):
            fixed.append((_decimal(cost["value"]), cost["currency"]))
    if fixed:
        # Le moins cher : c'est ce qu'un acheteur paie au minimum pour recevoir.
        cheapest = min(fixed, key=lambda pair: pair[0] or Decimal(0))
        shipping_amount, shipping_currency = cheapest

    location = item.get("itemLocation")
    country = location.get("country") if isinstance(location, dict) else None
    bid_count = item.get("bidCount")

    return Candidate(
        source=SOURCE_NAME,
        external_id=external_id,
        title=title,
        url=url,
        amount=amount,
        currency=currency.upper(),
        price_kind="current_bid" if is_auction else "asking",
        observed_at=now,
        listed_at=_timestamp(item.get("itemCreationDate")),
        ends_at=_timestamp(item.get("itemEndDate")) if is_auction else None,
        bid_count=bid_count if isinstance(bid_count, int) else None,
        shipping_amount=shipping_amount,
        shipping_currency=shipping_currency,
        country=country if isinstance(country, str) else None,
        condition_text=item.get("condition")
        if isinstance(item.get("condition"), str)
        else None,
        marketplace=marketplace,
        offers_accepted="BEST_OFFER" in options,
    )


class EbayBrowseSource:
    name = SOURCE_NAME

    def __init__(
        self,
        *,
        client_id: str | None,
        client_secret: str | None,
        marketplaces: list[str],
        policy: SearchPolicy,
        client: httpx.AsyncClient,
        environment: str = "production",
        base_url: str | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._marketplaces = marketplaces
        self._policy = policy
        self._client = client
        self._base = (
            base_url or _BASE_URLS.get(environment) or _BASE_URLS["production"]
        ).rstrip("/")
        self._sleep = sleep
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0

    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret and self._marketplaces)

    # -- jeton -----------------------------------------------------------

    async def _ensure_token(self, outcome: SourceOutcome) -> bool:
        if self._token and time.monotonic() < self._token_expires_at - 60:
            return True
        credentials = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode("ascii")
        started = time.monotonic()
        try:
            response = await self._client.post(
                f"{self._base}/identity/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials", "scope": _SCOPE},
                timeout=self._policy.request_timeout_s,
            )
        except httpx.HTTPError as error:
            outcome.requests.append(
                RequestRecord(
                    "jeton OAuth",
                    None,
                    round(time.monotonic() - started, 2),
                    type(error).__name__,
                )
            )
            outcome.status = "error"
            outcome.message = "eBay est injoignable (authentification)."
            return False
        outcome.requests.append(
            RequestRecord(
                "jeton OAuth",
                response.status_code,
                round(time.monotonic() - started, 2),
            )
        )
        if response.status_code in (400, 401):
            outcome.status = "blocked"
            outcome.message = (
                "eBay refuse les identifiants (clé ou secret invalides, ou clé de "
                "test utilisée en production). Aucune recherche n'a été émise."
            )
            return False
        if response.status_code == 429:
            outcome.status = "rate_limited"
            outcome.message = "Quota eBay atteint (authentification)."
            return False
        if response.status_code != 200:
            outcome.status = "error"
            outcome.message = (
                f"eBay a répondu {response.status_code} à l'authentification."
            )
            return False
        body = response.json()
        token = body.get("access_token")
        if not isinstance(token, str):
            outcome.status = "error"
            outcome.message = "Réponse d'authentification eBay inattendue."
            return False
        self._token = token
        self._token_expires_at = time.monotonic() + float(body.get("expires_in", 7200))
        return True

    # -- recherche -------------------------------------------------------

    def _queries(self, query: SearchQuery) -> list[str]:
        variants = spelling_variants(query.reference)
        # La forme telle que saisie, puis la forme compacte : ce sont les deux
        # écritures que les vendeurs emploient réellement.
        chosen = [variants[0]]
        if len(variants) > 1 and variants[1] != variants[0]:
            chosen.append(variants[1])
        return [f"{query.brand} {variant}" for variant in chosen]

    async def search(self, query: SearchQuery) -> SourceOutcome:
        outcome = SourceOutcome(source=SOURCE_NAME, status="ok")
        if not self.is_configured():
            outcome.status = "not_configured"
            outcome.message = (
                "Aucun identifiant eBay n'est configuré : la source n'a pas été "
                "interrogée."
            )
            return outcome

        budget = self._policy.max_requests_per_run
        if not await self._ensure_token(outcome):
            return outcome

        queries = self._queries(query)
        limit = min(self._policy.page_size, _PAGE_LIMIT_MAX)
        # Ensemble des combinaisons encore actives : une combinaison sans page
        # suivante sort de la liste, ce qui borne le nombre d'appels.
        active = [(m, q) for m in self._marketplaces for q in queries]
        failures: list[str] = []
        successes = 0

        for page in range(self._policy.max_pages_per_query):
            next_active: list[tuple[str, str]] = []
            for marketplace, text in active:
                if len(outcome.requests) >= budget:
                    outcome.status = "budget_exhausted"
                    outcome.message = (
                        f"Limite de {budget} requêtes par recherche atteinte : "
                        "résultats partiels."
                    )
                    return self._finish(outcome, failures, successes)

                if outcome.requests:
                    await self._sleep(self._policy.delay_between_requests_s)
                result = await self._page(
                    outcome, marketplace, text, page * limit, limit
                )
                if result == "stop":
                    return outcome
                if result == "failed":
                    failures.append(f"{marketplace}: requête en échec")
                    continue
                successes += 1
                if result == "more":
                    next_active.append((marketplace, text))
            active = next_active
            if not active:
                break
        return self._finish(outcome, failures, successes)

    def _finish(
        self, outcome: SourceOutcome, failures: list[str], successes: int
    ) -> SourceOutcome:
        if outcome.status == "ok" and failures:
            if successes == 0:
                outcome.status = "error"
                outcome.message = "Toutes les requêtes eBay ont échoué."
            else:
                outcome.message = (
                    "Résultats partiels : " + "; ".join(sorted(set(failures))) + "."
                )
        return outcome

    async def _page(
        self,
        outcome: SourceOutcome,
        marketplace: str,
        text: str,
        offset: int,
        limit: int,
    ) -> str:
        """`more` s'il y a une page suivante, `done`, `failed`, ou `stop`."""

        label = f"{marketplace} « {text} » (page {offset // limit + 1})"
        started = time.monotonic()
        try:
            response = await self._client.get(
                f"{self._base}/buy/browse/v1/item_summary/search",
                params={"q": text, "limit": limit, "offset": offset},
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "X-EBAY-C-MARKETPLACE-ID": marketplace,
                    "Accept": "application/json",
                },
                timeout=self._policy.request_timeout_s,
            )
        except httpx.HTTPError as error:
            outcome.requests.append(
                RequestRecord(
                    label,
                    None,
                    round(time.monotonic() - started, 2),
                    type(error).__name__,
                )
            )
            return "failed"

        outcome.requests.append(
            RequestRecord(
                label, response.status_code, round(time.monotonic() - started, 2)
            )
        )
        status = response.status_code
        if status in (401, 403):
            outcome.status = "blocked"
            outcome.message = (
                f"eBay a refusé l'accès (HTTP {status}) : source arrêtée, "
                "aucune nouvelle tentative."
            )
            return "stop"
        if status == 429:
            outcome.status = "rate_limited"
            outcome.message = "Quota eBay atteint (HTTP 429) : source arrêtée."
            return "stop"
        if status >= 500 or status != 200:
            return "failed"

        try:
            body = response.json()
        except ValueError:
            return "failed"
        now = self._clock()
        for item in body.get("itemSummaries", []) or []:
            if isinstance(item, dict):
                parsed = parse_item(item, marketplace, now)
                if parsed is not None:
                    outcome.candidates.append(parsed)
        return "more" if body.get("next") else "done"
