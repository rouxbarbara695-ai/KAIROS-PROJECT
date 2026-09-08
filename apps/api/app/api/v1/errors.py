from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm.exc import StaleDataError

from app.shared.domain.errors import DomainError, ErrorCode, http_status

_log = structlog.get_logger()

# Code d'erreur PostgreSQL levé par les déclencheurs d'immuabilité
# (`raise exception ... using errcode = '55000'`).
_OBJECT_NOT_IN_PREREQUISITE_STATE = "55000"
_UNIQUE_VIOLATION = "23505"
_CHECK_VIOLATION = "23514"
_FOREIGN_KEY_VIOLATION = "23503"
_NOT_NULL_VIOLATION = "23502"


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

    @app.exception_handler(StaleDataError)
    async def handle_stale_data(request: Request, exc: StaleDataError) -> JSONResponse:
        """La ligne a changé entre la lecture et l'écriture.

        `version_id_col` ajoute `where version = <valeur lue>` à chaque
        `UPDATE` d'opportunité. Zéro ligne touchée signifie qu'une autre
        transaction a écrit entre-temps : c'est le conflit que `If-Match`
        annonce, constaté cette fois par la base plutôt que par le contrôle
        préalable. Le message de SQLAlchemy cite la table et le nombre de
        lignes ; il ne sort pas d'ici.
        """

        _log.info("version_conflict", request_id=_request_id(request))
        return JSONResponse(
            status_code=409,
            content=_envelope(
                ErrorCode.RESOURCE_VERSION_CONFLICT,
                "Le dossier a changé pendant l'enregistrement. Recharger, "
                "vérifier ce qui a bougé, puis renvoyer la correction.",
                _request_id(request),
                details={"reason": "concurrent_write"},
            ),
        )

    @app.exception_handler(DBAPIError)
    async def handle_database_error(request: Request, exc: DBAPIError) -> JSONResponse:
        """Traduit une contrainte violée en erreur du catalogue.

        Sans cela, une contrainte que le code n'a pas anticipée ressort en
        `500` avec, dans les journaux, la requête et ses paramètres — donc
        potentiellement un numéro de série, que la règle 11 interdit d'y voir
        figurer. Ici, le client reçoit un code du catalogue et **rien** du
        détail SQL : ni nom de contrainte, ni requête, ni valeur soumise. Le
        `request_id` suffit à retrouver l'incident côté serveur.
        """

        original = getattr(exc, "orig", None)
        code = getattr(original, "sqlstate", None) or getattr(
            getattr(original, "diag", None), "sqlstate", None
        )

        catalogue = {
            _OBJECT_NOT_IN_PREREQUISITE_STATE: (
                ErrorCode.IMMUTABLE_RESOURCE,
                "Cette ressource est figée : elle ne se modifie pas, une "
                "nouvelle version la remplace.",
            ),
            _UNIQUE_VIOLATION: (
                ErrorCode.VALIDATION_ERROR,
                "Une ressource identique existe déjà.",
            ),
            _CHECK_VIOLATION: (
                ErrorCode.VALIDATION_ERROR,
                "Une valeur soumise sort du domaine autorisé.",
            ),
            _FOREIGN_KEY_VIOLATION: (
                ErrorCode.VALIDATION_ERROR,
                "Une ressource référencée est introuvable ou appartient à un "
                "autre portefeuille.",
            ),
            _NOT_NULL_VIOLATION: (
                ErrorCode.VALIDATION_ERROR,
                "Une donnée obligatoire manque.",
            ),
        }

        known = catalogue.get(str(code))
        # Journalisé : l'état SQL et le nom de la contrainte, qui sont du
        # schéma. **Pas** l'exception SQLAlchemy : son texte contient la
        # requête et ses paramètres, donc potentiellement un numéro de série
        # — précisément ce que la règle 11 interdit d'écrire dans un journal.
        # Le `request_id` relie cette ligne à la requête pour le diagnostic.
        _log.warning(
            "database_constraint",
            request_id=_request_id(request),
            sqlstate=str(code),
            constraint=getattr(
                getattr(original, "diag", None), "constraint_name", None
            ),
            translated=known is not None,
        )

        if known is None:
            return JSONResponse(
                status_code=500,
                content=_envelope(
                    ErrorCode.INTERNAL_ERROR,
                    "L'enregistrement a échoué. L'incident est journalisé.",
                    _request_id(request),
                ),
            )

        error_code, message = known
        return JSONResponse(
            status_code=http_status(error_code),
            content=_envelope(error_code, message, _request_id(request)),
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
