import json
from pathlib import Path

from app.main import app

_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[4] / "packages" / "contracts" / "openapi.json"
)


def test_openapi_schema_matches_committed_snapshot() -> None:
    current = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    committed = _SNAPSHOT_PATH.read_text()
    assert current == committed, (
        "Le schéma OpenAPI a divergé du contrat committé. "
        "Regénérer avec `make contracts` si le changement est voulu."
    )
