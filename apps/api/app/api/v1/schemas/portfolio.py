from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.v1.schemas.common import DecimalString


class LedgerMovementCreate(BaseModel):
    """Mouvement de trésorerie saisi par l'utilisateur.

    Seules les natures sans contrepartie ailleurs sont acceptées. Un paiement
    d'achat ou un encaissement de vente a sa ligne dans `purchases` ou
    `sales` : le saisir ici ferait diverger le registre des opérations qu'il
    reflète.

    Le montant est toujours positif — c'est la nature qui porte le sens, comme
    dans le registre lui-même.
    """

    kind: Literal[
        "capital_contribution",
        "withdrawal",
        "positive_adjustment",
        "negative_adjustment",
    ]
    amount: DecimalString
    currency: str = Field(min_length=3, max_length=3)
    occurred_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)


class LedgerMovementResponse(BaseModel):
    """Une écriture du registre, avec la traçabilité de change qu'exige la
    règle 3 : devise source, montant EUR, taux, source et horodatage."""

    id: uuid.UUID
    kind: str
    amount_source: DecimalString
    currency: str
    amount_eur: DecimalString
    rate_to_eur: DecimalString
    fx_source: str
    fx_rate_at: datetime
    occurred_at: datetime
    notes: str | None = None
    created_at: datetime


class HoldingResponse(BaseModel):
    opportunity_id: uuid.UUID
    brand: str | None = None
    reference: str | None = None
    cost_eur: DecimalString
    purchased_at: datetime


class PortfolioOverviewResponse(BaseModel):
    """Trésorerie, stock et détail.

    Le stock est détaillé plutôt que résumé : annoncer un taux
    d'immobilisation sans dire quelles montres immobilisent le capital ne dit
    pas quoi vendre.
    """

    portfolio_id: uuid.UUID
    available_cash_eur: DecimalString
    stock_at_cost_eur: DecimalString
    total_capital_eur: DecimalString
    holdings: list[HoldingResponse]
    movements: list[LedgerMovementResponse]


class StrategyUpdate(BaseModel):
    """Ajustement de la stratégie.

    Chaque champ est facultatif : ceux qu'on ne mentionne pas sont repris de
    la version courante. Une stratégie se corrige d'un paramètre à la fois ;
    exiger la saisie complète inviterait à la faute de recopie.

    `resale_platform_code` est la plateforme où l'on compte revendre — une
    décision, pas une propriété de l'annonce achetée. `clear_resale_platform`
    la retire explicitement, ce qu'un champ vide ne saurait exprimer sans
    ambiguïté.
    """

    minimum_roi: DecimalString | None = None
    minimum_profit_eur: DecimalString | None = None
    maximum_allocation_rate: DecimalString | None = None
    negotiation_buffer: DecimalString | None = None
    resale_platform_code: str | None = None
    clear_resale_platform: bool = False


class StrategyResponse(BaseModel):
    id: uuid.UUID
    version: int
    valid_from: datetime
    minimum_roi: DecimalString
    minimum_profit_eur: DecimalString
    maximum_allocation_rate: DecimalString
    negotiation_buffer: DecimalString
    resale_platform_code: str | None = None
