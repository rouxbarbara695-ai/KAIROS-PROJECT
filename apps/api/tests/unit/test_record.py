from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.scoring.domain.record import record_completeness
from app.shared.domain.errors import DomainError
from app.shared.rules.ruleset import Ruleset

_SEED = Path(__file__).parents[4] / "database" / "schema.sql"
_FIELDS = [
    "brand",
    "reference",
    "reference_status",
    "mechanical_condition",
    "cosmetic_condition",
    "originality",
    "box",
    "papers",
    "price",
    "seller_country",
    "seller_type",
    "platform",
]


@pytest.fixture(scope="module")
def ruleset() -> Ruleset:
    """Reproduit `1.2.0` : le barème seedé plus la liste de champs qu'ajoute
    la migration 0003."""

    sql = _SEED.read_text(encoding="utf-8")
    start = sql.index("'{", sql.index("with seed(version, config, valid_from)")) + 1
    end = sql.index("'::jsonb", start)
    config = json.loads(sql[start:end], parse_float=Decimal)
    config["scoring"]["record_fields"] = _FIELDS
    return Ruleset(version="1.2.0", config=config)


def test_a_complete_record_scores_one_hundred(ruleset: Ruleset) -> None:
    result = record_completeness(dict.fromkeys(_FIELDS, True), ruleset)
    assert result.score == Decimal("100.00")
    assert result.missing == ()


def test_the_score_is_the_ratio_of_filled_to_applicable(ruleset: Ruleset) -> None:
    fields = dict.fromkeys(_FIELDS, True)
    fields["papers"] = False
    fields["seller_type"] = False
    fields["platform"] = False

    result = record_completeness(fields, ruleset)
    # 9 renseignés sur 12 applicables.
    assert result.score == Decimal("75.00")
    assert set(result.missing) == {"papers", "seller_type", "platform"}


def test_a_field_without_object_leaves_the_denominator(ruleset: Ruleset) -> None:
    """Reprocher l'absence de plateforme à une vente de particulier à
    particulier reviendrait à noter un dossier complet comme incomplet."""

    fields: dict[str, bool | None] = dict.fromkeys(_FIELDS, True)
    fields["platform"] = None

    result = record_completeness(fields, ruleset)
    assert result.score == Decimal("100.00")
    assert result.not_applicable == ("platform",)


def test_the_result_says_which_field_is_missing(ruleset: Ruleset) -> None:
    """Annoncer 92 % sans dire quoi corriger demande à l'utilisateur de
    deviner."""

    fields = dict.fromkeys(_FIELDS, True)
    fields["reference"] = False

    result = record_completeness(fields, ruleset)
    assert result.missing == ("reference",)
    assert "reference" not in result.filled


def test_an_unlisted_field_is_refused(ruleset: Ruleset) -> None:
    """La note doit dépendre du barème versionné, pas du code : un champ que
    le barème ignore ne peut pas peser dessus."""

    with pytest.raises(DomainError):
        record_completeness({"numero_de_serie": True}, ruleset)


def test_an_omitted_field_counts_as_missing(ruleset: Ruleset) -> None:
    """Un champ que l'appelant ne mentionne pas est vide, pas sans objet :
    l'oubli ne doit pas améliorer la note."""

    result = record_completeness({"brand": True}, ruleset)
    assert result.score == Decimal("8.33")
    assert len(result.missing) == 11


def test_a_ruleset_without_the_list_fails_loudly(ruleset: Ruleset) -> None:
    stripped = Ruleset(
        version="1.0.0",
        config={**ruleset.config, "scoring": {}},
    )
    with pytest.raises(DomainError):
        record_completeness({"brand": True}, stripped)
