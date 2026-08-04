from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Catalogue unique — doit rester synchronisé avec
    docs/architecture/api-contract.md."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    OPPORTUNITY_DUPLICATE = "OPPORTUNITY_DUPLICATE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    RESOURCE_VERSION_CONFLICT = "RESOURCE_VERSION_CONFLICT"
    IMMUTABLE_RESOURCE = "IMMUTABLE_RESOURCE"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    REFERENCE_UNCONFIRMED = "REFERENCE_UNCONFIRMED"
    GATE_FAILED = "GATE_FAILED"
    VALUATION_INSUFFICIENT_COMPARABLES = "VALUATION_INSUFFICIENT_COMPARABLES"
    FX_RATE_UNAVAILABLE = "FX_RATE_UNAVAILABLE"
    COLLECTOR_NOT_AUTHORIZED = "COLLECTOR_NOT_AUTHORIZED"
    COLLECTOR_UNAVAILABLE = "COLLECTOR_UNAVAILABLE"
    RULESET_MISSING = "RULESET_MISSING"
    RATE_LIMITED = "RATE_LIMITED"


_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.OPPORTUNITY_DUPLICATE: 409,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.RESOURCE_VERSION_CONFLICT: 409,
    ErrorCode.IMMUTABLE_RESOURCE: 409,
    ErrorCode.INVALID_TRANSITION: 409,
    ErrorCode.REFERENCE_UNCONFIRMED: 422,
    ErrorCode.GATE_FAILED: 422,
    ErrorCode.VALUATION_INSUFFICIENT_COMPARABLES: 422,
    ErrorCode.FX_RATE_UNAVAILABLE: 503,
    ErrorCode.COLLECTOR_NOT_AUTHORIZED: 403,
    ErrorCode.COLLECTOR_UNAVAILABLE: 503,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.RULESET_MISSING: 500,
}


class DomainError(Exception):
    """Toute erreur métier qui doit atteindre le client sous la forme du
    catalogue. Ne jamais laisser fuiter une exception technique brute."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS[self.code]
