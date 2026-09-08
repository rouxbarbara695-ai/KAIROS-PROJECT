"""Comparaison de version, côté métier.

Séparée de l'en-tête HTTP qui la transporte : la règle — « on ne corrige pas
un dossier qu'on n'a pas lu dans son état actuel » — appartient au domaine,
pas à l'adaptateur.
"""

from __future__ import annotations

from app.shared.domain.errors import DomainError, ErrorCode


def check_version(expected: int, actual: int) -> None:
    """Refuse une correction fondée sur une lecture périmée.

    Contrôle **préalable**, pas garantie : entre cette comparaison et
    l'écriture, une transaction concurrente peut encore passer. La garantie
    est le `where version = …` que l'ORM ajoute à l'`UPDATE`. Ce contrôle-ci
    sert à rendre l'erreur immédiate et lisible, et à ne pas engager de
    travail — écriture d'audit comprise — pour une correction déjà périmée.
    """

    if expected != actual:
        raise DomainError(
            ErrorCode.RESOURCE_VERSION_CONFLICT,
            "Le dossier a changé depuis la lecture. Recharger, vérifier ce qui "
            "a bougé, puis renvoyer la correction.",
            details={"expected_version": expected, "current_version": actual},
        )
