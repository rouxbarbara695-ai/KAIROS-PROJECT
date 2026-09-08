"""Récupération d'une page distante, sous contrainte.

Ce qui distingue cet adaptateur d'un `httpx.get` :

- **les redirections ne sont pas suivies par la bibliothèque.** Chaque saut
  est revalidé comme une URL neuve, sinon un domaine autorisé qui redirige
  vers `127.0.0.1` suffirait à faire tomber tout le garde-fou ;
- **le nom est résolu avant la connexion** et toutes ses adresses sont
  vérifiées. Un nom public qui pointe vers le réseau interne est refusé ;
- **le corps est lu par morceaux** et la lecture s'arrête au-delà de la
  taille maximale. Se fier à `Content-Length` ne protège de rien : un serveur
  hostile l'annonce à zéro et envoie un gigaoctet ;
- **le délai d'attente est global**, pas par opération : dix secondes de
  connexion suivies de dix secondes de lecture feraient vingt secondes
  d'attente devant un formulaire vide.

Il reste une limite qu'il faut nommer plutôt que masquer : entre la résolution
du nom et la connexion, `httpx` résout à nouveau. Un attaquant maîtrisant le
DNS pourrait, en théorie, répondre différemment aux deux résolutions. Fermer
cette fenêtre demande de se connecter à l'adresse vérifiée en forçant l'en-tête
`Host`, ce qui casse la vérification du certificat TLS. Le choix retenu — liste
blanche de domaines **plus** vérification des adresses — rend l'attaque
inaccessible sans contrôler d'abord l'un des domaines autorisés.
"""

from __future__ import annotations

import asyncio
import socket

import httpx
import structlog

from app.collection.domain.url_guard import (
    MAX_BYTES,
    MAX_REDIRECTS,
    TIMEOUT_SECONDS,
    check_addresses,
    check_shape,
)
from app.collection.ports.fetcher import FetchedPage
from app.shared.domain.errors import DomainError, ErrorCode

_log = structlog.get_logger()

# Se présenter honnêtement. Un agent qui se déguise en navigateur pour passer
# un contrôle contournerait ce contrôle, ce que la validation d'accès interdit
# explicitement.
USER_AGENT = "KAIROS/1.0 (+récupération unitaire à la demande de l'utilisateur)"

_ACCEPTED_TYPES = ("text/html", "application/xhtml+xml", "application/ld+json")


async def _resolve(host: str) -> tuple[str, ...]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise DomainError(
            ErrorCode.COLLECTOR_UNAVAILABLE,
            f"Le domaine {host} est introuvable.",
            details={"reason": "dns_failure"},
        ) from exc
    return tuple(dict.fromkeys(str(info[4][0]) for info in infos))


class HttpFetcher:
    """Récupère une page, ou explique précisément pourquoi elle ne vient pas."""

    async def fetch(self, url: str, allowed_hosts: frozenset[str]) -> FetchedPage:
        current = url
        for hop in range(MAX_REDIRECTS + 1):
            host = check_shape(current, allowed_hosts)
            check_addresses(host, await _resolve(host))

            response = await self._request(current)

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise DomainError(
                        ErrorCode.COLLECTOR_UNAVAILABLE,
                        "Redirection sans destination.",
                        details={"reason": "redirect_without_location"},
                    )
                # Résolue contre l'URL courante : une redirection relative est
                # légitime et fréquente.
                current = str(httpx.URL(current).join(location))
                _log.info("collect_redirect", hop=hop, host=host)
                continue

            return self._page(current, response)

        raise DomainError(
            ErrorCode.COLLECTOR_UNAVAILABLE,
            "Trop de redirections successives.",
            details={"reason": "too_many_redirects"},
        )

    async def _request(self, url: str) -> httpx.Response:
        try:
            async with (
                httpx.AsyncClient(
                    follow_redirects=False,
                    timeout=httpx.Timeout(TIMEOUT_SECONDS),
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                    },
                ) as client,
                client.stream("GET", url) as response,
            ):
                body = await self._read_limited(response)
                response._content = body  # noqa: SLF001 - lecture bornée
                return response
        except httpx.TimeoutException as exc:
            raise DomainError(
                ErrorCode.COLLECTOR_UNAVAILABLE,
                "La page n'a pas répondu dans le délai imparti.",
                details={"reason": "timeout"},
            ) from exc
        except httpx.HTTPError as exc:
            # Le message de la bibliothèque peut contenir l'URL complète ; on
            # ne le renvoie pas, seule la catégorie sort.
            raise DomainError(
                ErrorCode.COLLECTOR_UNAVAILABLE,
                "La page n'a pas pu être jointe.",
                details={"reason": "network_error"},
            ) from exc

    @staticmethod
    async def _read_limited(response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > MAX_BYTES:
                raise DomainError(
                    ErrorCode.COLLECTOR_UNAVAILABLE,
                    "La page dépasse la taille maximale acceptée.",
                    details={"reason": "too_large"},
                )
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _page(url: str, response: httpx.Response) -> FetchedPage:
        content_type = response.headers.get("content-type", "").split(";")[0].strip()

        if response.status_code >= 400:
            raise _refused(response, content_type)

        if content_type and not any(
            content_type.startswith(kind) for kind in _ACCEPTED_TYPES
        ):
            raise DomainError(
                ErrorCode.COLLECTOR_UNAVAILABLE,
                "Cette adresse ne renvoie pas une page web.",
                details={"reason": "unexpected_content_type", "type": content_type},
            )

        return FetchedPage(
            final_url=url,
            status_code=response.status_code,
            content_type=content_type,
            text=response.text,
        )


def _refused(response: httpx.Response, content_type: str) -> DomainError:
    """Traduit un refus du serveur distant en explication utilisable.

    Le cas qui compte est le contrôle anti-robot : il ne se corrige pas en
    réessayant, et le contourner est exclu. L'utilisateur doit donc apprendre
    tout de suite qu'il faut passer par l'import assisté, plutôt que de voir
    une erreur générique et recommencer.
    """

    status = response.status_code
    challenge = (
        response.headers.get("cf-mitigated") == "challenge"
        or "datadome" in response.headers.get("set-cookie", "").lower()
        or status in (401, 403, 429)
    )

    if challenge:
        return DomainError(
            ErrorCode.COLLECTOR_NOT_AUTHORIZED,
            "Cette plateforme protège ses pages contre les accès automatisés. "
            "KAIROS ne contourne pas cette protection : ouvrir l'annonce dans "
            "le navigateur et utiliser l'import assisté.",
            details={
                "reason": "protected_by_platform",
                "status": status,
                "fallback": "assisted_import",
            },
        )

    if status == 404:
        return DomainError(
            ErrorCode.NOT_FOUND,
            "Cette annonce n'existe pas ou a été retirée.",
            details={"reason": "listing_gone", "status": status},
        )

    return DomainError(
        ErrorCode.COLLECTOR_UNAVAILABLE,
        "La plateforme n'a pas rendu la page.",
        details={"reason": "upstream_error", "status": status},
    )
