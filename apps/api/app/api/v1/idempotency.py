"""Raccordement de l'idempotence aux routes.

L'en-tête `Idempotency-Key` est **facultatif**, comme le dit le contrat API :
une requête qui n'en porte pas se comporte exactement comme avant. C'est ce qui
permet de livrer le mécanisme sans casser le moindre appel existant.

La route déclare l'en-tête avec l'alias `IdempotencyKey`, ce qui le fait
apparaître dans l'OpenAPI — donc dans les types partagés du client — plutôt que
de le laisser lu en douce dans les en-têtes de la requête.

Le gardien s'emploie ainsi :

    async with idempotency.guard(
        request, portfolio_id, OpportunityResponse, key
    ) as place:
        if place.replay is not None:
            return place.replay
        resultat = await operation(...)
        return place.completed(resultat)

Le troisième argument est le type que la route rend. Il ne sert qu'au typage :
la réponse conservée est du JSON, et c'est FastAPI qui la revalide contre le
`response_model` de la route au moment du rejeu. L'écrire au point d'appel dit
explicitement sous quelle forme le rejeu doit ressortir.

Le gestionnaire de contexte libère la clé si l'opération lève. C'est délibéré :
un échec n'a pas de résultat à rejouer, et l'utilisateur doit pouvoir réessayer
avec la même clé.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Generic, TypeVar, cast

from fastapi import Header, Request
from fastapi.encoders import jsonable_encoder

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.idempotency import KEY_MAX_LENGTH, KEY_MIN_LENGTH, fingerprint
from app.shared.infrastructure.db.session import get_session_factory
from app.shared.infrastructure.idempotency import (
    IdempotencyStore,
    InProgress,
    Mismatch,
    Replay,
    Reserved,
)

HEADER = "Idempotency-Key"

# Déclaré comme paramètre d'en-tête pour que le contrat le publie. Facultatif :
# une requête sans clé se comporte exactement comme avant.
IdempotencyKey = Annotated[
    str | None,
    Header(
        alias=HEADER,
        description=(
            "Clé fournie par l'appelant pour qu'un renvoi de la même requête "
            "ne répète pas ses effets. Le renvoi rend la réponse d'origine ; "
            "la même clé sur une requête différente est refusée."
        ),
    ),
]

T = TypeVar("T")


class Place(Generic[T]):
    """Une place réservée pour une requête.

    `replay` porte la réponse d'origine quand la même requête a déjà abouti ;
    il vaut `None` dans tous les autres cas, y compris lorsque aucune clé n'a
    été fournie.
    """

    def __init__(self, replay: T | None = None) -> None:
        self.replay = replay
        self.result: T | None = None
        self.recorded = False

    def completed(self, result: T) -> T:
        """Désigne le résultat à conserver, et le rend inchangé.

        Il n'est écrit qu'à la sortie du gestionnaire de contexte : à ce moment
        seulement, on sait que l'opération n'a pas levé.
        """

        self.result = result
        self.recorded = True
        return result


def _status_for(request: Request) -> int:
    """Statut que la route produit. Une même route en produit toujours le même,
    donc le rejeu retrouve naturellement celui de la réponse d'origine."""

    route = request.scope.get("route")
    return int(getattr(route, "status_code", None) or 200)


class Idempotency:
    def __init__(self, store: IdempotencyStore) -> None:
        self._store = store

    @asynccontextmanager
    async def guard(
        self,
        request: Request,
        portfolio_id: uuid.UUID,
        produces: type[T],
        key: str | None,
    ) -> AsyncIterator[Place[T]]:
        if key is None:
            yield Place[T]()
            return

        if not KEY_MIN_LENGTH <= len(key) <= KEY_MAX_LENGTH:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                f"`{HEADER}` doit contenir entre {KEY_MIN_LENGTH} et "
                f"{KEY_MAX_LENGTH} caractères.",
                field=HEADER,
            )

        outcome = await self._store.reserve(
            portfolio_id=portfolio_id,
            key=key,
            method=request.method,
            path=request.url.path,
            # Le corps est déjà lu et mis en cache par Starlette au moment où
            # FastAPI a construit le modèle de la requête : ce second accès ne
            # relit pas le réseau.
            request_hash=fingerprint(await request.body()),
        )

        if isinstance(outcome, Replay):
            # Le corps conservé est du JSON. FastAPI le fera passer par le
            # `response_model` de la route, qui lui rendra sa forme.
            yield Place(replay=cast(T, outcome.body))
            return

        if isinstance(outcome, InProgress):
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "Une requête portant cette clé est déjà en cours. Attendre sa "
                "réponse plutôt que de la renvoyer.",
                details={"reason": "in_progress"},
            )

        if isinstance(outcome, Mismatch):
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "Cette clé a déjà servi pour une requête différente. Employer "
                "une nouvelle clé pour une nouvelle opération.",
                details={
                    "reason": "payload_mismatch",
                    "previous_method": outcome.previous_method,
                    "previous_path": outcome.previous_path,
                },
            )

        assert isinstance(outcome, Reserved)
        place: Place[T] = Place()
        try:
            yield place
        except BaseException:
            await self._store.release(outcome.record_id)
            raise

        if place.recorded:
            await self._store.complete(
                outcome.record_id,
                status_code=_status_for(request),
                body=jsonable_encoder(place.result),
            )
        else:
            # La route est sortie sans annoncer de résultat : rien à rejouer,
            # et garder la clé empêcherait une reprise légitime.
            await self._store.release(outcome.record_id)


def get_idempotency() -> Idempotency:
    return Idempotency(IdempotencyStore(get_session_factory()))
