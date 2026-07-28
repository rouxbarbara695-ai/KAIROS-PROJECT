from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

from app.shared.domain.errors import DomainError, ErrorCode

T = TypeVar("T")

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class CursorPosition:
    """Position d'un curseur : (created_at, id), tri created_at DESC, id DESC
    (docs/architecture/api-contract.md)."""

    created_at: datetime
    id: str


def encode_cursor(position: CursorPosition) -> str:
    payload = {"created_at": position.created_at.isoformat(), "id": position.id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> CursorPosition:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload: dict[str, Any] = json.loads(raw)
        return CursorPosition(
            created_at=datetime.fromisoformat(payload["created_at"]),
            id=str(payload["id"]),
        )
    except Exception as exc:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Curseur de pagination invalide.",
            field="cursor",
        ) from exc


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR, "limit doit être >= 1.", field="limit"
        )
    return min(limit, MAX_LIMIT)


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    items: list[T]
    next_cursor: str | None
