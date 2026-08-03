from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.platforms import Platform, PlatformRule


async def record_platform_rule(
    session: AsyncSession,
    principal: Principal,
    platform_code: str,
    *,
    region_code: str,
    buyer_fee_rate: Decimal | None,
    buyer_fee_fixed: Decimal | None,
    buyer_fee_min: Decimal | None,
    buyer_fee_max: Decimal | None,
    seller_fee_rate: Decimal | None,
    seller_fee_fixed: Decimal | None,
    seller_fee_min: Decimal | None,
    seller_fee_max: Decimal | None,
    buyer_fee_vat_rate: Decimal | None,
    seller_fee_vat_rate: Decimal | None,
    payment_fee_rate: Decimal | None,
    buyer_fee_tiers: list[dict[str, object]],
    seller_fee_tiers: list[dict[str, object]],
    buyer_fee_basis: str,
    seller_fee_basis: str,
    currency: str,
    provenance_url: str,
) -> PlatformRule:
    """Enregistre une grille de frais, en nouvelle version.

    Une grille n'est jamais modifiée : on ferme la précédente et on en ouvre
    une autre. Une analyse produite sous l'ancienne grille reste ainsi
    rejouable — c'est la même discipline que pour les barèmes.

    Les montants viennent de l'utilisateur, jamais d'une valeur par défaut :
    inventer une commission fausserait tous les profits d'un portefeuille sans
    que rien ne le signale (CLAUDE.md règle 1). `provenance_url` est exigée
    pour que la grille reste vérifiable.
    """

    platform = (
        await session.execute(select(Platform).where(Platform.code == platform_code))
    ).scalar_one_or_none()
    if platform is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Plateforme inconnue.")

    now = datetime.now(UTC)

    current = (
        await session.execute(
            select(PlatformRule)
            .where(
                PlatformRule.platform_id == platform.id,
                PlatformRule.region_code == region_code,
                or_(PlatformRule.valid_to.is_(None), PlatformRule.valid_to > now),
            )
            .order_by(PlatformRule.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if current is not None:
        # Fermer avant d'ouvrir : la contrainte d'exclusion interdit deux
        # grilles valides au même moment, et elle a raison — deux commissions
        # simultanées rendraient le coût indéterminé.
        current.valid_to = now
        await session.flush()

    highest = (
        await session.execute(
            select(PlatformRule.version)
            .where(
                PlatformRule.platform_id == platform.id,
                PlatformRule.region_code == region_code,
            )
            .order_by(PlatformRule.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    rule = PlatformRule(
        platform_id=platform.id,
        region_code=region_code,
        version=(highest or 0) + 1,
        valid_from=now,
        # Saisir une grille de frais n'autorise aucune collecte. Le mode
        # d'accès et son autorisation relèvent d'une validation écrite
        # distincte (CLAUDE.md règle 9) : les laisser ouverts ici
        # transformerait un formulaire de tarifs en feu vert de collecte.
        access_method="manual",
        access_authorized=False,
        buyer_fee_rate=buyer_fee_rate,
        buyer_fee_fixed=buyer_fee_fixed,
        buyer_fee_currency=currency.upper() if buyer_fee_fixed is not None else None,
        buyer_fee_min=buyer_fee_min,
        buyer_fee_max=buyer_fee_max,
        seller_fee_rate=seller_fee_rate,
        seller_fee_fixed=seller_fee_fixed,
        seller_fee_currency=currency.upper() if seller_fee_fixed is not None else None,
        seller_fee_min=seller_fee_min,
        seller_fee_max=seller_fee_max,
        buyer_fee_vat_rate=buyer_fee_vat_rate,
        seller_fee_vat_rate=seller_fee_vat_rate,
        payment_fee_rate=payment_fee_rate,
        buyer_fee_tiers=buyer_fee_tiers,
        seller_fee_tiers=seller_fee_tiers,
        buyer_fee_basis=buyer_fee_basis,
        seller_fee_basis=seller_fee_basis,
        provenance_url=provenance_url,
        created_by_user_id=principal.user_id,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def list_platforms(
    session: AsyncSession,
) -> list[tuple[Platform, PlatformRule | None]]:
    """Les plateformes et, pour chacune, sa grille en vigueur s'il y en a une.

    Une plateforme sans grille n'est pas un détail : une opportunité qui en
    vient ne peut pas être analysée, faute de pouvoir établir ses coûts.
    """

    now = datetime.now(UTC)
    platforms = list(
        (await session.execute(select(Platform).order_by(Platform.code))).scalars()
    )

    rules = list(
        (
            await session.execute(
                select(PlatformRule).where(
                    PlatformRule.valid_from <= now,
                    or_(PlatformRule.valid_to.is_(None), PlatformRule.valid_to > now),
                )
            )
        ).scalars()
    )
    by_platform: dict[uuid.UUID, PlatformRule] = {
        rule.platform_id: rule for rule in rules
    }

    return [(platform, by_platform.get(platform.id)) for platform in platforms]
