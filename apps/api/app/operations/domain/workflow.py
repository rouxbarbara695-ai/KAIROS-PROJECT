"""Machine à états d'une opportunité (`workflow-and-states.md`).

Fonction pure : elle ne connaît ni FastAPI ni la base. Les transitions sont
recopiées de la spécification, sans ajout — un raccourci qui paraîtrait commode
ici deviendrait une règle métier inventée (CLAUDE.md règle 1).
"""

from __future__ import annotations

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.infrastructure.db.models.enums import OpportunityStatus as Status

# Recopie littérale du tableau de `workflow-and-states.md`. La réouverture
# d'une opportunité abandonnée revient à `watching` et exige un motif, ce que
# la couche appelante impose déjà pour toute transition.
_TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.WATCHING: frozenset({Status.BUY, Status.AUCTION, Status.ABANDONED}),
    Status.BUY: frozenset({Status.PURCHASED, Status.WATCHING, Status.ABANDONED}),
    Status.AUCTION: frozenset({Status.PURCHASED, Status.WATCHING, Status.ABANDONED}),
    Status.PURCHASED: frozenset({Status.IN_STOCK}),
    Status.IN_STOCK: frozenset({Status.LISTED_FOR_SALE}),
    Status.LISTED_FOR_SALE: frozenset({Status.AWAITING_BUYER_PAYMENT, Status.IN_STOCK}),
    Status.AWAITING_BUYER_PAYMENT: frozenset(
        {Status.AWAITING_PAYOUT, Status.LISTED_FOR_SALE}
    ),
    Status.AWAITING_PAYOUT: frozenset({Status.SOLD, Status.LISTED_FOR_SALE}),
    Status.SOLD: frozenset(),
    Status.ABANDONED: frozenset({Status.WATCHING}),
}


def allowed_transitions(current: Status) -> frozenset[Status]:
    """Ce vers quoi l'opportunité peut aller depuis son statut actuel.

    Exposé pour que l'interface propose exactement les gestes possibles plutôt
    que de les proposer tous et d'en refuser certains après coup.
    """

    return _TRANSITIONS[current]


def ensure_transition(current: Status, target: Status) -> None:
    """Vérifie qu'une transition est prévue, et échoue sinon.

    `sold` est terminal : une vente ne se défait pas, elle se corrige par une
    écriture inverse. Le refus est explicite plutôt que silencieux — un statut
    changé en douce rendrait l'historique d'audit incapable d'expliquer ce que
    le portefeuille détient.
    """

    if target == current:
        raise DomainError(
            ErrorCode.INVALID_TRANSITION,
            f"L'opportunité est déjà au statut « {current.value} ».",
            details={"status": current.value},
        )

    permitted = _TRANSITIONS[current]
    if target not in permitted:
        raise DomainError(
            ErrorCode.INVALID_TRANSITION,
            f"Passer de « {current.value} » à « {target.value} » n'est pas une "
            "transition prévue.",
            details={
                "status": current.value,
                "allowed": sorted(status.value for status in permitted),
            },
        )
