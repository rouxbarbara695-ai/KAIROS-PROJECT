"""Génère packages/contracts/openapi.json depuis l'application FastAPI.

Usage: python -m app.export_openapi <chemin_de_sortie>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m app.export_openapi <chemin_de_sortie>", file=sys.stderr)
        raise SystemExit(2)

    output_path = Path(sys.argv[1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
