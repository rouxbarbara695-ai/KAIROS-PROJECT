"""Génère database/schema-after-migrations.json depuis une base migrée.

Usage: python -m app.export_schema_snapshot <chemin_de_sortie>

La base désignée par `DATABASE_URL` doit être à jour (`alembic upgrade head`)
avant l'appel : cet outil photographie ce qu'il trouve, il ne migre rien.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from app.shared.config import get_settings
from app.shared.infrastructure.db.schema_snapshot import capture_schema


async def _capture(output_path: Path) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url.get_secret_value())
    try:
        async with engine.connect() as connection:
            snapshot = await capture_schema(connection)
    finally:
        await engine.dispose()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    print(f"Instantané écrit : {output_path}")


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m app.export_schema_snapshot <chemin_de_sortie>",
            file=sys.stderr,
        )
        return 2

    asyncio.run(_capture(Path(sys.argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
