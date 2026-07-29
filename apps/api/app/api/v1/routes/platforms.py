from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.common import DecimalString
from app.platforms.application.platform_rules_lookup import get_applicable_rule
from app.platforms.application.record_platform_rule import (
    list_platforms,
    record_platform_rule,
)
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.platforms import PlatformRule
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.principal_provider import get_current_principal

router = APIRouter(tags=["platforms"])


@router.get("/platforms/{code}/rules")
async def get_platform_rules_route(
    code: str,
    region: str = Query(default="*"),
    at: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    rule = await get_applicable_rule(session, code, region, at or datetime.now(UTC))
    return {
        "platform_code": code,
        "region_code": rule.region_code,
        "version": rule.version,
        "valid_from": rule.valid_from.isoformat(),
        "valid_to": rule.valid_to.isoformat() if rule.valid_to else None,
        "access_method": rule.access_method,
        "access_authorized": rule.access_authorized,
        "buyer_fee_rate": str(rule.buyer_fee_rate) if rule.buyer_fee_rate else None,
        "seller_fee_rate": str(rule.seller_fee_rate) if rule.seller_fee_rate else None,
    }


class PlatformRuleCreate(BaseModel):
    """Grille de frais saisie à la main.

    Aucun champ n'a de valeur par défaut : inventer une commission fausserait
    tous les profits d'un portefeuille sans que rien ne le signale. Tout
    laisser vide est accepté — c'est une plateforme sans frais, et c'est un
    constat, pas un oubli.

    `provenance_url` est obligatoire : une grille qu'on ne peut pas vérifier
    ne vaut pas mieux qu'une grille inventée.
    """

    region_code: str = "*"
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    provenance_url: str = Field(min_length=1)

    buyer_fee_rate: DecimalString | None = None
    buyer_fee_fixed: DecimalString | None = None
    buyer_fee_min: DecimalString | None = None
    buyer_fee_max: DecimalString | None = None

    seller_fee_rate: DecimalString | None = None
    seller_fee_fixed: DecimalString | None = None
    seller_fee_min: DecimalString | None = None
    seller_fee_max: DecimalString | None = None

    @model_validator(mode="after")
    def _check_bounds(self) -> PlatformRuleCreate:
        for side, low, high in (
            ("buyer", self.buyer_fee_min, self.buyer_fee_max),
            ("seller", self.seller_fee_min, self.seller_fee_max),
        ):
            if low is not None and high is not None and low > high:
                raise ValueError(
                    f"Le plancher de commission {side} dépasse son plafond."
                )
        return self


class PlatformRuleResponse(BaseModel):
    id: uuid.UUID
    platform_code: str
    region_code: str
    version: int
    valid_from: datetime
    valid_to: datetime | None = None
    access_method: str
    access_authorized: bool
    provenance_url: str | None = None

    buyer_fee_rate: DecimalString | None = None
    buyer_fee_fixed: DecimalString | None = None
    buyer_fee_min: DecimalString | None = None
    buyer_fee_max: DecimalString | None = None

    seller_fee_rate: DecimalString | None = None
    seller_fee_fixed: DecimalString | None = None
    seller_fee_min: DecimalString | None = None
    seller_fee_max: DecimalString | None = None


class PlatformResponse(BaseModel):
    code: str
    name: str
    has_active_rule: bool
    active_rule: PlatformRuleResponse | None = None


def _rule_response(code: str, rule: PlatformRule) -> PlatformRuleResponse:
    return PlatformRuleResponse(
        id=rule.id,
        platform_code=code,
        region_code=rule.region_code,
        version=rule.version,
        valid_from=rule.valid_from,
        valid_to=rule.valid_to,
        access_method=rule.access_method,
        access_authorized=rule.access_authorized,
        provenance_url=rule.provenance_url,
        buyer_fee_rate=rule.buyer_fee_rate,
        buyer_fee_fixed=rule.buyer_fee_fixed,
        buyer_fee_min=rule.buyer_fee_min,
        buyer_fee_max=rule.buyer_fee_max,
        seller_fee_rate=rule.seller_fee_rate,
        seller_fee_fixed=rule.seller_fee_fixed,
        seller_fee_min=rule.seller_fee_min,
        seller_fee_max=rule.seller_fee_max,
    )


@router.get("/platforms", response_model=list[PlatformResponse])
async def list_platforms_route(
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(get_current_principal),
) -> list[PlatformResponse]:
    """Plateformes connues et grille en vigueur pour chacune.

    Une plateforme sans grille est signalée comme telle : une opportunité qui
    en vient ne peut pas être analysée, faute de pouvoir établir ses coûts.
    """

    return [
        PlatformResponse(
            code=platform.code,
            name=platform.name,
            has_active_rule=rule is not None,
            active_rule=None if rule is None else _rule_response(platform.code, rule),
        )
        for platform, rule in await list_platforms(session)
    ]


@router.post(
    "/platforms/{code}/rules",
    status_code=status.HTTP_201_CREATED,
    response_model=PlatformRuleResponse,
)
async def create_platform_rule_route(
    code: str,
    body: PlatformRuleCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> PlatformRuleResponse:
    """Enregistre une grille de frais, en nouvelle version.

    La précédente est fermée, jamais réécrite : une analyse produite sous
    l'ancienne grille reste rejouable.
    """

    rule = await record_platform_rule(
        session,
        principal,
        code,
        region_code=body.region_code,
        buyer_fee_rate=body.buyer_fee_rate,
        buyer_fee_fixed=body.buyer_fee_fixed,
        buyer_fee_min=body.buyer_fee_min,
        buyer_fee_max=body.buyer_fee_max,
        seller_fee_rate=body.seller_fee_rate,
        seller_fee_fixed=body.seller_fee_fixed,
        seller_fee_min=body.seller_fee_min,
        seller_fee_max=body.seller_fee_max,
        currency=body.currency,
        provenance_url=body.provenance_url,
    )
    return _rule_response(code, rule)
