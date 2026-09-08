"""Registre des clés d'idempotence, arbitré par PostgreSQL.

**Le point qui compte : c'est l'index unique qui tranche, pas le code.**

Un contrôle écrit naïvement — « la clé existe-t-elle ? sinon, insère » — laisse
une fenêtre entre la lecture et l'écriture. Deux requêtes simultanées la
franchissent toutes les deux et créent deux opérations : exactement ce que
l'idempotence devait empêcher, et sur les écritures financières le double clic
est précisément le cas fréquent.

Ici, la réservation est un `insert ... on conflict do nothing`. La contrainte
`(portfolio_id, idempotency_key)` désigne un gagnant, une fois pour toutes. Le
perdant apprend qu'il a perdu par le fait que rien n'a été inséré.

Le registre vit dans **sa propre transaction**, séparée de celle de l'opération
métier. C'est nécessaire : une réservation qui ne serait visible qu'après le
commit de l'opération n'arrêterait aucune requête concurrente, puisque la
concurrence se produit précisément pendant que l'opération tourne.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.domain.idempotency import IN_PROGRESS_TIMEOUT, RETENTION
from app.shared.infrastructure.db.models.jobs import IdempotencyRecord


@dataclass(frozen=True, slots=True)
class Reserved:
    """La clé est à nous : l'opération doit être exécutée."""

    record_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class Replay:
    """La même requête a déjà abouti : sa réponse est rendue telle quelle."""

    status_code: int
    body: Any


@dataclass(frozen=True, slots=True)
class InProgress:
    """La même requête est en cours ailleurs."""


@dataclass(frozen=True, slots=True)
class Mismatch:
    """La clé a déjà servi, pour une requête différente."""

    previous_method: str
    previous_path: str


@dataclass(frozen=True, slots=True)
class _Reclaimed:
    """Signal interne : une place périmée a été libérée, il faut réinsérer."""


Outcome = Reserved | Replay | InProgress | Mismatch


class IdempotencyStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def reserve(
        self,
        *,
        portfolio_id: uuid.UUID,
        key: str,
        method: str,
        path: str,
        request_hash: str,
    ) -> Outcome:
        """Tente de prendre la clé, et dit ce qu'il en est.

        Deux passes au plus. La première peut libérer une réservation périmée
        ou abandonnée ; la seconde réinsère alors. Si elle échoue à son tour,
        c'est qu'une autre requête a pris la place entre-temps — le cas est
        traité comme n'importe quelle concurrence, sans boucler.
        """

        for allow_reclaim in (True, False):
            async with self._factory() as session:
                outcome = await self._attempt(
                    session,
                    portfolio_id=portfolio_id,
                    key=key,
                    method=method,
                    path=path,
                    request_hash=request_hash,
                    allow_reclaim=allow_reclaim,
                )
                await session.commit()

            if not isinstance(outcome, _Reclaimed):
                return outcome

        return InProgress()  # pragma: no cover - deux reprises consécutives

    async def _attempt(
        self,
        session: AsyncSession,
        *,
        portfolio_id: uuid.UUID,
        key: str,
        method: str,
        path: str,
        request_hash: str,
        allow_reclaim: bool,
    ) -> Outcome | _Reclaimed:
        now = datetime.now(UTC)

        inserted = (
            await session.execute(
                insert(IdempotencyRecord)
                .values(
                    portfolio_id=portfolio_id,
                    idempotency_key=key,
                    request_method=method,
                    request_path=path,
                    request_hash=request_hash,
                    expires_at=now + RETENTION,
                )
                .on_conflict_do_nothing(
                    index_elements=["portfolio_id", "idempotency_key"]
                )
                .returning(IdempotencyRecord.id)
            )
        ).scalar_one_or_none()

        if inserted is not None:
            return Reserved(inserted)

        existing = (
            await session.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.portfolio_id == portfolio_id,
                    IdempotencyRecord.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()

        if existing is None:  # pragma: no cover - la ligne a disparu entre-temps
            return _Reclaimed() if allow_reclaim else InProgress()

        abandoned = (
            existing.response_status is None
            and now - existing.created_at > IN_PROGRESS_TIMEOUT
        )
        if allow_reclaim and (existing.expires_at <= now or abandoned):
            await session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.id == existing.id)
            )
            return _Reclaimed()

        if (
            existing.request_method != method
            or existing.request_path != path
            or existing.request_hash != request_hash
        ):
            return Mismatch(existing.request_method, existing.request_path)

        if existing.response_status is None:
            return InProgress()

        return Replay(existing.response_status, existing.response_body)

    async def complete(
        self, record_id: uuid.UUID, *, status_code: int, body: Any
    ) -> None:
        async with self._factory() as session:
            await session.execute(
                update(IdempotencyRecord)
                .where(IdempotencyRecord.id == record_id)
                .values(response_status=status_code, response_body=body)
            )
            await session.commit()

    async def release(self, record_id: uuid.UUID) -> None:
        """Libère la clé après un échec.

        Une opération qui a échoué n'a pas de résultat à rejouer, et
        l'utilisateur doit pouvoir réessayer avec la même clé. Conserver la
        réservation transformerait une panne passagère en clé brûlée : le
        renvoi serait refusé alors que rien n'a été écrit.
        """

        async with self._factory() as session:
            await session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.id == record_id)
            )
            await session.commit()
