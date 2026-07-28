from __future__ import annotations

import logging
import sys
from typing import Any, cast

import structlog
from structlog.typing import EventDict, WrappedLogger

_SENSITIVE_KEYS = {
    "authorization",
    "token",
    "password",
    "secret",
    "serial_number",
    "serial_number_encrypted",
    "database_url",
    "redis_url",
    "cursor_secret",
}

_MASK = "***"


def _mask_sensitive(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Empêche tout secret ou numéro de série d'atteindre les logs
    (CLAUDE.md règle 11 ; PRD §6)."""

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: (_MASK if k.lower() in _SENSITIVE_KEYS else scrub(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return {
        k: (_MASK if k.lower() in _SENSITIVE_KEYS else scrub(v))
        for k, v in event_dict.items()
    }


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            _mask_sensitive,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_values: Any) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(**initial_values))
