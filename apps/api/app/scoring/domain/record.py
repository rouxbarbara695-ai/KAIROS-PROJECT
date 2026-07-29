from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.rules.ruleset import Ruleset

_SUBSCORE = Decimal("0.01")
_RECORD_FIELDS = ("scoring", "record_fields")


@dataclass(frozen=True, slots=True)
class RecordCompleteness:
    """Qualité de la fiche : champs renseignés sur champs applicables.

    Les deux listes sont conservées, pas seulement le rapport. Un utilisateur
    à qui l'on annonce 62 % doit pouvoir voir *quel* champ manque, sinon le
    score lui demande de deviner ce qu'il faut corriger.
    """

    score: Decimal
    filled: tuple[str, ...]
    missing: tuple[str, ...]
    not_applicable: tuple[str, ...]


def record_completeness(
    fields: Mapping[str, bool | None], ruleset: Ruleset
) -> RecordCompleteness:
    """Note la fiche selon `scoring.record_fields` (scoring-engine.md § 1).

    `True` renseigné, `False` applicable mais vide, `None` sans objet pour ce
    dossier. Un champ sans objet n'entre ni au numérateur ni au dénominateur :
    reprocher l'absence d'une plateforme à une vente de particulier à
    particulier reviendrait à pénaliser un dossier complet.
    """

    declared = ruleset.value(*_RECORD_FIELDS)
    if not isinstance(declared, list) or not declared:
        raise DomainError(
            ErrorCode.RULESET_MISSING,
            "La liste des champs de fiche est absente du barème.",
        )

    unknown = set(fields) - set(declared)
    if unknown:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Champs de fiche hors barème : la note deviendrait dépendante du "
            f"code plutôt que du barème versionné ({', '.join(sorted(unknown))}).",
        )

    filled: list[str] = []
    missing: list[str] = []
    not_applicable: list[str] = []

    for name in declared:
        state = fields.get(str(name), False)
        if state is None:
            not_applicable.append(str(name))
        elif state:
            filled.append(str(name))
        else:
            missing.append(str(name))

    applicable = len(filled) + len(missing)
    if applicable == 0:
        # Aucun champ applicable : le rapport n'existe pas. Rendre 0 laisserait
        # croire à une fiche vide, rendre 100 à une fiche parfaite.
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Aucun champ de fiche n'est applicable : la qualité de la fiche "
            "n'a pas de sens pour ce dossier.",
        )

    score = (Decimal(len(filled)) * Decimal("100") / Decimal(applicable)).quantize(
        _SUBSCORE, rounding=ROUND_HALF_UP
    )

    return RecordCompleteness(
        score=score,
        filled=tuple(filled),
        missing=tuple(missing),
        not_applicable=tuple(not_applicable),
    )
