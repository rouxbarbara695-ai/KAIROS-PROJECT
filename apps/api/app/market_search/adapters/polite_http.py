"""Client HTTP poli pour les sources qui publient des pages.

Ce que ce client garantit, dans cet ordre :

1. **robots.txt est lu, et obéi.** Un chemin interdit n'est jamais requêté. Un
   robots.txt illisible (protégé, en erreur) arrête la source : l'incertitude ne
   vaut pas permission (RFC 9309). C'est une condition **nécessaire**, jamais
   suffisante : un robot autorisé n'est pas un droit de stockage.
2. **Le rythme est celui de la source.** Délai entre deux requêtes = le plus
   grand du réglage de KAIROS et du `crawl-delay` publié par la source.
3. **Un refus explicite arrête la source.** 401, 403, 429, défi anti-robot
   (`cf-mitigated`) : `SourceStop`, sans nouvelle tentative et sans contournement.
4. **Chaque requête est consignée**, avec son statut HTTP : c'est la preuve de ce
   qui a été interrogé.
5. **Le corps est plafonné**, et l'agent est honnête (`KAIROS/…`, jamais un
   navigateur).
"""

from __future__ import annotations

import asyncio
import time
import urllib.robotparser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.collection.adapters.http_fetcher import USER_AGENT
from app.market_search.domain.candidate import (
    RequestRecord,
    SourceOutcome,
    SourceStatus,
)
from app.market_search.domain.policy import SearchPolicy

_CHALLENGE_HEADERS = ("cf-mitigated",)


class SourceStop(Exception):
    """La source doit s'arrêter : refus explicite, robots, quota."""

    def __init__(self, status: SourceStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True, slots=True)
class Page:
    status: int
    text: str
    url: str


class PoliteClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        outcome: SourceOutcome,
        policy: SearchPolicy,
        *,
        min_delay_s: float = 0.0,
        max_requests: int | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._outcome = outcome
        self._policy = policy
        self._min_delay = max(min_delay_s, policy.page_source_min_delay_s)
        self._max_requests = max_requests or policy.page_source_max_requests
        self._sleep = sleep
        self._monotonic = monotonic
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._delays: dict[str, float] = {}

    # -- robots ------------------------------------------------------------

    async def _ensure_robots(self, host: str, scheme: str) -> None:
        if host in self._robots:
            return
        page = await self._request(
            f"{scheme}://{host}/robots.txt", label=f"robots.txt de {host}", check=False
        )
        parser = urllib.robotparser.RobotFileParser()
        if page.status == 200:
            parser.parse(page.text.splitlines())
        elif page.status in (401, 403, 429):
            raise SourceStop(
                "blocked",
                f"robots.txt de {host} inaccessible (HTTP {page.status}) : "
                "source arrêtée, aucune recherche émise.",
            )
        elif 400 <= page.status < 500:
            # Aucun robots.txt : rien n'est interdit (RFC 9309).
            parser.parse([])
        else:
            raise SourceStop(
                "error",
                f"robots.txt de {host} indisponible (HTTP {page.status}) : "
                "source arrêtée par prudence.",
            )
        self._robots[host] = parser
        crawl = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*")
        self._delays[host] = float(crawl) if crawl else 0.0

    # -- requêtes ----------------------------------------------------------

    async def get(
        self,
        url: str,
        *,
        label: str,
        params: dict[str, str | int] | None = None,
        robots: bool = True,
    ) -> Page:
        """`robots=False` seulement pour un point d'accès **machine** publié par la
        source elle-même (profil UCP `/.well-known/ucp`), qui n'est pas une page."""

        parts = urlsplit(url)
        target = url
        if params:
            target = str(httpx.URL(url, params=params))
        if robots:
            await self._ensure_robots(parts.netloc, parts.scheme)
            if not self._robots[parts.netloc].can_fetch(USER_AGENT, target):
                raise SourceStop(
                    "blocked",
                    f"Chemin interdit par le robots.txt de {parts.netloc} : "
                    "aucune requête émise.",
                )
        return await self._request(target, label=label, check=True)

    async def post_json(
        self, url: str, payload: dict[str, object], *, label: str
    ) -> Page:
        """Appel d'un protocole machine (JSON-RPC du catalogue UCP). Pas de
        robots.txt : ce n'est pas une page, c'est le canal que la boutique
        publie pour les agents. Le rythme et les refus sont traités comme
        ailleurs."""

        return await self._request(
            url, label=label, check=True, method="POST", payload=payload
        )

    async def _request(
        self,
        url: str,
        *,
        label: str,
        check: bool,
        method: str = "GET",
        payload: dict[str, object] | None = None,
    ) -> Page:
        if len(self._outcome.requests) >= self._max_requests:
            self._outcome.complete = False
            raise SourceStop(
                "budget_exhausted",
                f"Limite de {self._max_requests} requêtes par recherche atteinte : "
                "résultats partiels.",
            )
        host = urlsplit(url).netloc
        delay = max(self._min_delay, self._delays.get(host, 0.0))
        previous = self._last.get(host)
        if previous is not None:
            wait = delay - (self._monotonic() - previous)
            if wait > 0:
                await self._sleep(wait)
        started = self._monotonic()
        try:
            if method == "POST":
                response = await self._client.post(
                    url,
                    json=payload,
                    headers={"Accept": "application/json, text/event-stream"},
                    timeout=self._policy.request_timeout_s,
                )
            else:
                response = await self._client.get(
                    url,
                    headers={"Accept": "text/html,application/xhtml+xml"},
                    timeout=self._policy.request_timeout_s,
                    follow_redirects=True,
                )
        except httpx.HTTPError as error:
            self._last[host] = self._monotonic()
            self._outcome.requests.append(
                RequestRecord(
                    label,
                    None,
                    round(self._monotonic() - started, 2),
                    type(error).__name__,
                )
            )
            raise SourceStop(
                "error", f"{host} injoignable ({type(error).__name__})."
            ) from error
        self._last[host] = self._monotonic()
        self._outcome.requests.append(
            RequestRecord(
                label, response.status_code, round(self._monotonic() - started, 2)
            )
        )
        if check:
            self._raise_on_refusal(host, response)
        text = response.content[: self._policy.page_source_max_bytes].decode(
            response.encoding or "utf-8", "replace"
        )
        return Page(response.status_code, text, str(response.url))

    def _raise_on_refusal(self, host: str, response: httpx.Response) -> None:
        challenged = any(response.headers.get(h) for h in _CHALLENGE_HEADERS)
        if response.status_code == 429:
            raise SourceStop(
                "rate_limited",
                f"{host} limite le débit (HTTP 429) : source arrêtée.",
            )
        if response.status_code in (401, 403) or challenged:
            raise SourceStop(
                "blocked",
                f"{host} refuse l'accès (HTTP {response.status_code}"
                f"{', défi anti-robot' if challenged else ''}) : source arrêtée, "
                "aucune nouvelle tentative, aucun contournement.",
            )
