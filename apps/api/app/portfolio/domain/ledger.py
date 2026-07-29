from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.shared.domain.errors import DomainError, ErrorCode


class LedgerKind(StrEnum):
    """Nature d'un mouvement de trésorerie (`ledger_entry_kind` du schéma)."""

    CAPITAL_CONTRIBUTION = "capital_contribution"
    WITHDRAWAL = "withdrawal"
    PURCHASE_PAYMENT = "purchase_payment"
    COST_PAYMENT = "cost_payment"
    SALE_RECEIPT = "sale_receipt"
    REFUND = "refund"
    POSITIVE_ADJUSTMENT = "positive_adjustment"
    NEGATIVE_ADJUSTMENT = "negative_adjustment"


# Le sens de chaque nature est une propriété du registre, pas une convention
# d'affichage : il détermine la trésorerie disponible, donc l'allocation, donc
# le score. Une nature ajoutée au schéma sans sens déclaré ici doit faire
# échouer le calcul plutôt que d'être comptée à zéro en silence.
_SIGNS: dict[LedgerKind, Decimal] = {
    LedgerKind.CAPITAL_CONTRIBUTION: Decimal("1"),
    LedgerKind.SALE_RECEIPT: Decimal("1"),
    LedgerKind.REFUND: Decimal("1"),
    LedgerKind.POSITIVE_ADJUSTMENT: Decimal("1"),
    LedgerKind.WITHDRAWAL: Decimal("-1"),
    LedgerKind.PURCHASE_PAYMENT: Decimal("-1"),
    LedgerKind.COST_PAYMENT: Decimal("-1"),
    LedgerKind.NEGATIVE_ADJUSTMENT: Decimal("-1"),
}


# Natures qu'un utilisateur peut écrire directement.
#
# Les autres — paiement d'achat, paiement de coût, encaissement de vente,
# remboursement — ont une contrepartie ailleurs : une ligne dans `purchases`,
# `opportunity_costs` ou `sales`. Les saisir à la main laisserait le registre
# diverger des opérations qu'il est censé refléter, et la trésorerie
# cesserait de s'expliquer. Elles sont écrites par les parcours d'achat et de
# vente, jamais par ce formulaire.
TREASURY_KINDS = frozenset(
    {
        LedgerKind.CAPITAL_CONTRIBUTION,
        LedgerKind.WITHDRAWAL,
        LedgerKind.POSITIVE_ADJUSTMENT,
        LedgerKind.NEGATIVE_ADJUSTMENT,
    }
)


@dataclass(frozen=True, slots=True)
class LedgerMovement:
    """Un mouvement déjà converti en euros.

    Le montant est toujours positif : c'est la nature qui porte le sens. Un
    montant négatif rendrait deux représentations possibles pour un même
    mouvement, et le schéma l'interdit déjà (`amount_eur > 0`).
    """

    kind: LedgerKind
    amount_eur: Decimal

    def __post_init__(self) -> None:
        if self.amount_eur <= 0:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                "Le montant d'un mouvement doit être strictement positif : "
                "c'est la nature du mouvement qui en porte le sens.",
                field="amount_eur",
            )


def signed_amount(movement: LedgerMovement) -> Decimal:
    sign = _SIGNS.get(movement.kind)
    if sign is None:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            f"Nature de mouvement sans sens déclaré : {movement.kind}.",
            field="kind",
        )
    return sign * movement.amount_eur


def cash_balance(movements: Iterable[LedgerMovement]) -> Decimal:
    """Trésorerie disponible, somme signée du registre.

    Le solde peut être négatif — un découvert se constate, il ne se corrige
    pas au moment du calcul. C'est l'exposition qui refusera ensuite de
    mesurer une allocation sur une trésorerie nulle ou négative.
    """

    return sum(
        (signed_amount(movement) for movement in movements), start=Decimal("0.00")
    )
