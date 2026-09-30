"""Socle commun des sources qui lisent des pages publiques.

Une source concrète n'écrit que `_run` : quoi demander, comment lire la réponse.
Ce socle garantit le reste — configuration, client poli, arrêt sur refus, et
surtout : **`search` ne lève jamais**. Un échec est un statut, avec son
diagnostic, jamais une exception qui ferait perdre les résultats des autres
sources ni une liste vide qui se ferait passer pour « aucune annonce ».
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
import structlog

from app.market_search.adapters.polite_http import PoliteClient, SourceStop
from app.market_search.domain.candidate import SearchQuery, SourceOutcome
from app.market_search.domain.policy import SearchPolicy

logger = structlog.get_logger()


class HttpSource(ABC):
    name: str
    #: Délai propre à la source, en plus du `crawl-delay` de son robots.txt.
    min_delay_s: float = 0.0

    def __init__(
        self, client: httpx.AsyncClient, policy: SearchPolicy, **kwargs: object
    ) -> None:
        self._client = client
        self._policy = policy
        self._kwargs = kwargs

    def is_configured(self) -> bool:
        # Sources publiques : aucun identifiant. Leur activation passe par le
        # registre (`source_registry.py`), pas par un secret.
        return True

    def _polite(self, outcome: SourceOutcome) -> PoliteClient:
        return PoliteClient(
            self._client,
            outcome,
            self._policy,
            min_delay_s=self.min_delay_s,
            **self._kwargs,  # type: ignore[arg-type]
        )

    @abstractmethod
    async def _run(
        self, query: SearchQuery, outcome: SourceOutcome, http: PoliteClient
    ) -> None: ...

    async def search(self, query: SearchQuery) -> SourceOutcome:
        outcome = SourceOutcome(source=self.name, status="ok")
        try:
            await self._run(query, outcome, self._polite(outcome))
        except SourceStop as stop:
            outcome.status = stop.status
            outcome.message = stop.message
        except Exception as error:  # noqa: BLE001 — jamais d'exception hors d'une source
            logger.error(
                "source_failed", source=self.name, error_type=type(error).__name__
            )
            outcome.status = "error"
            outcome.message = (
                f"Lecture de {self.name} impossible (erreur inattendue : "
                f"{type(error).__name__})."
            )
        return outcome
