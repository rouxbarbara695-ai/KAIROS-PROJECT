from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.comparables import (
    ComparableCreate,
    ComparableImportResult,
    ComparableImportRow,
)
from app.market.application.create_comparable import create_comparable
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal

# Colonnes reconnues. Les absentes prennent la valeur par défaut du schéma ;
# une colonne inconnue est ignorée plutôt que de faire échouer tout le fichier.
_REQUIRED = ("source_name", "price_kind", "amount", "currency", "source_reliability")

_BOOLEAN_TRUE = frozenset({"1", "true", "vrai", "oui", "yes", "x"})
_BOOLEAN_FALSE = frozenset({"0", "false", "faux", "non", "no", ""})

_MAX_ROWS = 500


def _boolean(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in _BOOLEAN_TRUE:
        return True
    if normalized in _BOOLEAN_FALSE:
        return False
    raise ValueError(f"Valeur booléenne non reconnue : {value!r}.")


def _row_to_payload(row: dict[str, str]) -> ComparableCreate:
    cleaned = {
        key.strip(): (value.strip() if isinstance(value, str) else value)
        for key, value in row.items()
        if key
    }

    missing = [column for column in _REQUIRED if not cleaned.get(column)]
    if missing:
        raise ValueError(f"Colonnes obligatoires absentes : {', '.join(missing)}.")

    return ComparableCreate(
        source_name=cleaned["source_name"],
        source_external_id=cleaned.get("source_external_id") or None,
        seller_fingerprint=cleaned.get("seller_fingerprint") or None,
        price_kind=cleaned["price_kind"],
        amount=cleaned["amount"],
        currency=cleaned["currency"],
        market_status=cleaned.get("market_status") or "unknown",
        observed_at=(
            datetime.fromisoformat(cleaned["observed_at"])
            if cleaned.get("observed_at")
            else datetime.now(UTC)
        ),
        source_reliability=cleaned["source_reliability"].lower(),
        mechanical_condition=cleaned.get("mechanical_condition") or None,
        cosmetic_condition=cleaned.get("cosmetic_condition") or None,
        box=_boolean(cleaned.get("box")),
        papers=_boolean(cleaned.get("papers")),
    )


async def import_comparables(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    content: str,
    settings: Settings,
) -> ComparableImportResult:
    """Importe des comparables depuis un CSV.

    Les lignes valides sont enregistrées et les lignes fautives rapportées avec
    leur numéro : un fichier partiellement erroné ne fait pas perdre la saisie
    déjà correcte. Une ligne rejetée n'annule pas les précédentes, chaque
    création étant validée pour elle-même.
    """

    reader = csv.DictReader(io.StringIO(content))
    columns = {(name or "").strip() for name in reader.fieldnames or ()}

    # Un en-tête non reconnu est signalé une fois, en nommant ce qui manque.
    # Rapporter ligne à ligne un fichier entièrement inexploitable — ou pire,
    # répondre « 0 importé, 0 rejeté » — n'aiderait pas à le corriger.
    missing = [column for column in _REQUIRED if column not in columns]
    if missing:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            f"En-tête CSV incomplet. Colonnes attendues et absentes : "
            f"{', '.join(missing)}.",
            field="content",
            details={"missing_columns": missing},
        )

    imported = 0
    rejected: list[ComparableImportRow] = []

    for index, row in enumerate(reader, start=2):  # ligne 1 = en-tête
        if index - 1 > _MAX_ROWS:
            rejected.append(
                ComparableImportRow(
                    line=index,
                    error=f"Fichier tronqué au-delà de {_MAX_ROWS} lignes.",
                )
            )
            break

        try:
            payload = _row_to_payload(row)
        except (ValueError, ValidationError) as exc:
            rejected.append(ComparableImportRow(line=index, error=_first_message(exc)))
            continue

        try:
            await create_comparable(
                session, principal, opportunity_id, payload, settings
            )
        except DomainError as exc:
            if exc.code is ErrorCode.NOT_FOUND:
                # L'opportunité elle-même est introuvable : poursuivre ligne à
                # ligne n'aurait aucun sens.
                raise
            rejected.append(ComparableImportRow(line=index, error=exc.message))
            continue

        imported += 1

    return ComparableImportResult(imported=imported, rejected=rejected)


def _first_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        if errors:
            location = ".".join(str(part) for part in errors[0].get("loc", ()))
            return f"{location}: {errors[0].get('msg', 'valeur invalide')}".strip(": ")
    return str(exc)
