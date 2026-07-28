from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.domain.errors import DomainError, ErrorCode


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _sanitize_errors(errors: Any) -> list[dict[str, Any]]:
    """`RequestValidationError.errors()` inclut `ctx.error` (l'exception
    Python brute d'un `@model_validator`, non JSON-sérialisable) et `input`
    (la valeur soumise, qui ne doit jamais être renvoyée en écho — CLAUDE.md
    règle 11). On ne garde que `loc`, `msg` et `type`, tous sûrs."""

    return [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
        for e in errors
    ]


def _envelope(
    code: ErrorCode,
    message: str,
    request_id: str,
    field: str | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "error": {
            "code": code.value,
            "message": message,
            "field": field,
            "details": details or {},
            "request_id": request_id,
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_envelope(
                exc.code, exc.message, _request_id(request), exc.field, exc.details
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = _sanitize_errors(exc.errors())
        first_error = errors[0] if errors else {}
        field = ".".join(str(p) for p in first_error.get("loc", ()) if p != "body")
        return JSONResponse(
            status_code=422,
            content=_envelope(
                ErrorCode.VALIDATION_ERROR,
                first_error.get("msg", "Requête invalide."),
                _request_id(request),
                field or None,
                {"errors": errors},
            ),
        )
