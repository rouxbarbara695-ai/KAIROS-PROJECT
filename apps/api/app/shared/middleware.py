from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"

logger = structlog.get_logger()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Lit ou génère X-Request-Id, l'attache au contexte de log et le
    renvoie en en-tête. Le corps de réponse porte aussi `request_id`
    (ajouté par les gestionnaires de route/erreur)."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        started_at = time.monotonic()

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, route=request.url.path
        )

        response = await call_next(request)

        duration_ms = round((time.monotonic() - started_at) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "http_request",
            status=response.status_code,
            duration_ms=duration_ms,
            method=request.method,
        )
        return response
