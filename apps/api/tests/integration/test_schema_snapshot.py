"""Le schéma migré doit correspondre à l'instantané committé.

Ce test remplace la comparaison `pg_dump` / `database/schema.sql` que la CI
exécutait avec `|| true`. Elle ne pouvait rien détecter : elle opposait deux
styles d'écriture, et surtout deux objets différents — le schéma **initial**
d'un côté, l'état **après toutes les migrations** de l'autre.

Ce qui est vérifié ici est la seule comparaison qui ait un sens : la structure
obtenue en rejouant toutes les migrations, contre une photographie committée de
cette même structure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.db.schema_snapshot import capture_schema

pytestmark = pytest.mark.integration

_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[4] / "database" / "schema-after-migrations.json"
)


async def test_migrated_schema_matches_committed_snapshot(
    db_session: AsyncSession,
) -> None:
    connection = await db_session.connection()
    current = await capture_schema(connection)

    committed = json.loads(_SNAPSHOT_PATH.read_text())

    # Comparaison par sections plutôt qu'en bloc : un échec doit dire *ce* qui
    # a dérivé. Un `assert current == committed` sur trois cents contraintes
    # produirait un diff illisible que personne ne lirait.
    assert current["enums"] == committed["enums"], (
        "Les types énumérés ont changé. Régénérer avec `make schema-snapshot` "
        "si le changement est voulu."
    )
    assert current["triggers"] == committed["triggers"], (
        "Les déclencheurs ont changé. Ce sont eux qui portent l'immuabilité "
        "(append-only, analyse publiée, autorisation des collecteurs) : vérifier "
        "qu'aucune protection n'a disparu avant de régénérer l'instantané."
    )

    assert set(current["tables"]) == set(committed["tables"]), (
        "La liste des tables a changé. Régénérer avec `make schema-snapshot` "
        "si le changement est voulu."
    )

    for table in sorted(current["tables"]):
        for section in ("columns", "constraints", "indexes"):
            assert (
                current["tables"][table][section]
                == (committed["tables"][table][section])
            ), (
                f"Le schéma de `{table}` a dérivé sur « {section} ». "
                "Régénérer avec `make schema-snapshot` si le changement est voulu."
            )


async def test_snapshot_records_the_immutability_triggers(
    db_session: AsyncSession,
) -> None:
    """L'instantané doit réellement contenir les protections, pas seulement des
    tables.

    Sans ce contrôle, une régénération faite après une suppression accidentelle
    de déclencheur figerait la perte au lieu de la signaler : l'instantané
    deviendrait complice de la dérive qu'il est censé détecter.
    """

    connection = await db_session.connection()
    snapshot = await capture_schema(connection)

    noms = {
        nom for declencheurs in snapshot["triggers"].values() for nom in declencheurs
    }

    assert "audit_events_append_only" in noms
    assert "analyses_published_immutable" in noms
    assert "collection_jobs_authorized" in noms
    assert "platform_rules_close_only" in noms
    assert "portfolio_ledger_entries_append_only" in noms
