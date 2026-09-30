"""Recalcul automatique de la cote et de l'analyse (workflow-and-states.md).

Un comparable ajouté, importé, corrigé, exclu ou réintégré change ce que le
marché dit de cette montre. La spécification en fait un déclencheur de
recalcul : sans lui, l'utilisateur devait presser deux boutons dans l'ordre
pour que le verdict suive ses propres saisies, et le moteur donnait
l'impression d'un simple inventaire.

Ce module n'invente aucune règle de calcul. Il enchaîne deux fonctions qui
existent — la cote, puis l'analyse — et décide seulement de **quand** les
appeler.

Le comparable est enregistré **avant** ce recalcul, dans sa propre transaction.
Un recalcul qui échoue ne doit jamais faire perdre une saisie : l'échec est
rendu à l'appelant sous forme de résultat, pas d'exception.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.application.compute_valuation import compute_valuation
from app.market.application.list_comparables import list_comparables
from app.scoring.application.run_analysis import run_analysis
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal

logger = structlog.get_logger()

# Même plafond que la route de cote manuelle : la cote porte sur l'ensemble des
# comparables de la référence, pas sur une page d'affichage.
_MAX_COMPARABLES = 500

# Valeur écrite dans `analyses.trigger_type`. La colonne est un texte libre ;
# `manual` reste réservé à la demande explicite de l'utilisateur.
TRIGGER = "comparable_changed"

Status = Literal["recalculated", "valuation_only", "skipped", "failed"]


@dataclass(frozen=True, slots=True)
class Recalculation:
    """Ce qui s'est passé, dit sans ambiguïté.

    - `recalculated` : une cote et une analyse neuves existent ;
    - `valuation_only` : la cote est à jour, l'analyse n'a pas pu l'être ;
    - `skipped` : il n'y avait rien à calculer (pas assez de comparables) ;
    - `failed` : échec inattendu, le comparable, lui, est bien enregistré.

    `reason` est un code stable, lisible par la machine ; `detail` est la phrase
    pour l'utilisateur.
    """

    status: Status
    reason: str | None = None
    detail: str | None = None
    valuation_id: uuid.UUID | None = None
    analysis_id: uuid.UUID | None = None


async def recalculate_after_comparable_change(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    settings: Settings,
) -> Recalculation:
    """Recalcule la cote, puis l'analyse, après un changement de comparables.

    Ne lève jamais : l'appelant a déjà enregistré ce qui a déclenché le calcul.
    """

    try:
        page = await list_comparables(
            session, principal, opportunity_id, _MAX_COMPARABLES, None
        )
        valuation = await compute_valuation(
            session, principal, opportunity_id, settings, list(page.items)
        )
    except DomainError as error:
        await session.rollback()
        if error.code is ErrorCode.VALUATION_INSUFFICIENT_COMPARABLES:
            # Pas une panne : avec un seul comparable, il n'y a pas de cote à
            # calculer, et le dire vaut mieux que fabriquer un chiffre.
            return Recalculation(
                status="skipped",
                reason="insufficient_comparables",
                detail=error.message,
            )
        return Recalculation(
            status="failed", reason=error.code.value, detail=error.message
        )
    except Exception as error:  # noqa: BLE001 — jamais d'exception vers l'appelant
        await session.rollback()
        return _unexpected(error, opportunity_id, "valuation")

    # L'identifiant est noté ici, tout de suite : un `commit` ou un `rollback`
    # périme les objets de la session, et relire `valuation.id` ensuite
    # déclencherait une lecture de base interdite dans ce contexte.
    valuation_id = valuation.id

    try:
        analysis = await run_analysis(
            session, principal, opportunity_id, settings, trigger_type=TRIGGER
        )
    except IntegrityError:
        # L'index unique sur `previous_analysis_id` n'autorise qu'un enfant par
        # analyse : un recalcul concurrent a gagné la course. Son résultat est
        # tout aussi valide que celui-ci — et l'écraser n'est pas une option.
        await session.rollback()
        return Recalculation(
            status="valuation_only",
            reason="concurrent_recalculation",
            detail="Un recalcul simultané a déjà publié l'analyse.",
            valuation_id=valuation_id,
        )
    except DomainError as error:
        # Cote à jour, analyse impossible : typiquement aucun prix en euros,
        # ou une donnée d'entrée manquante. La cote reste précieuse.
        await session.rollback()
        return Recalculation(
            status="valuation_only",
            reason=error.code.value,
            detail=error.message,
            valuation_id=valuation_id,
        )
    except Exception as error:  # noqa: BLE001
        await session.rollback()
        result = _unexpected(error, opportunity_id, "analysis")
        return Recalculation(
            status="valuation_only",
            reason=result.reason,
            detail=result.detail,
            valuation_id=valuation_id,
        )

    return Recalculation(
        status="recalculated", valuation_id=valuation_id, analysis_id=analysis.id
    )


def _unexpected(
    error: Exception, opportunity_id: uuid.UUID, stage: str
) -> Recalculation:
    """Échec imprévu : on le journalise sans jamais joindre la trace complète.

    Une exception SQLAlchemy embarque la requête *et ses paramètres* : la
    journaliser en entier pourrait écrire un numéro de série dans les logs, ce
    que la règle 11 interdit. Le type et l'étape suffisent à enquêter.
    """

    logger.error(
        "recalculation_failed",
        stage=stage,
        error_type=type(error).__name__,
        opportunity_id=str(opportunity_id),
    )
    return Recalculation(
        status="failed",
        reason="unexpected_error",
        detail=(
            "Le recalcul automatique a échoué. Le comparable est enregistré ; "
            "relancez le calcul à la main."
        ),
    )
