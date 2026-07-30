from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import cast, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.opportunities.application.get_opportunity import get_opportunity
from app.portfolio.application.position import current_position
from app.pricing.domain.costs import Cost, CostMode, CostPhase, Scenario
from app.pricing.domain.platform_costs import PlatformFees
from app.scoring.application.analysis_inputs import (
    AnalysisOutcome,
    MarketFacts,
    StrategyTerms,
    TransactionCosts,
    WatchFacts,
    analyse,
)
from app.scoring.application.strategy import RESALE_PLATFORM, active_strategy_version
from app.scoring.domain.record import RecordCompleteness, record_completeness
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.analyses import Analysis
from app.shared.infrastructure.db.models.listings import Listing
from app.shared.infrastructure.db.models.market import (
    Comparable,
    MarketValuation,
    ValuationComparable,
)
from app.shared.infrastructure.db.models.operations import OpportunityCost
from app.shared.infrastructure.db.models.platforms import Platform, PlatformRule
from app.shared.infrastructure.db.models.reference_data import Ruleset as RulesetRow
from app.shared.infrastructure.db.models.strategies import StrategyVersion
from app.shared.infrastructure.db.models.watches import Seller, Watch, WatchReference
from app.shared.infrastructure.ruleset_loader import load_ruleset
from app.shared.rules.ruleset import Ruleset


@dataclass(frozen=True, slots=True)
class _Counts:
    used: int
    dated: int
    total_weight: Decimal


async def _comparable_counts(session: AsyncSession, valuation_id: uuid.UUID) -> _Counts:
    """Ce que la cote a réellement utilisé.

    Les comparables écartés — par décision humaine ou comme anomalie — ne
    comptent ni dans la profondeur ni dans le poids : la porte « support de
    marché » doit voir la même chose que le calcul.
    """

    rows = (
        await session.execute(
            select(
                ValuationComparable.final_weight,
                Comparable.observed_at,
            )
            .join(Comparable, Comparable.id == ValuationComparable.comparable_id)
            .where(
                ValuationComparable.valuation_id == valuation_id,
                ValuationComparable.excluded.is_(False),
            )
        )
    ).all()

    return _Counts(
        used=len(rows),
        dated=sum(1 for _, observed_at in rows if observed_at is not None),
        total_weight=sum((weight for weight, _ in rows), start=Decimal("0")),
    )


def _dispersion(valuation: MarketValuation) -> Decimal:
    """Sous-score de dispersion, repris tel quel de la valorisation.

    Le recalculer ici produirait deux vérités pour un même nombre. Une cote
    sans ce sous-score est une cote d'une version antérieure du moteur : mieux
    vaut refuser que substituer une valeur plausible.
    """

    confidence = valuation.explanation.get("confidence")
    if isinstance(confidence, dict) and "dispersion" in confidence:
        return Decimal(str(confidence["dispersion"]))

    raise DomainError(
        ErrorCode.VALIDATION_ERROR,
        "La cote ne porte pas de sous-score de dispersion : recalculez la "
        "valorisation avant d'analyser.",
    )


def _seller_facts(seller: Seller | None) -> tuple[str, str, str, str | None]:
    """Risque, fiabilité, protections et pays du vendeur.

    Sans vendeur renseigné, tout est « inconnu » — jamais « bon ». Un dossier
    muet ne vaut pas un dossier rassurant.
    """

    if seller is None:
        return "unknown", "unknown", "none", None

    data = seller.reliability_data
    return (
        str(data.get("risk_level", "unknown")),
        str(data.get("reliability", "unknown")),
        str(data.get("protections", "none")),
        seller.country_code,
    )


def _operational_costs(rows: list[OpportunityCost]) -> tuple[Cost, ...]:
    """Coûts saisis pour ce dossier — révision, polissage, transport.

    Ils sont exceptionnels : on achète et on revend le plus souvent sans
    intervention. Quand ils existent, ils portent leur propre incertitude, d'où
    les trois montants distincts.
    """

    costs: list[Cost] = []
    for row in rows:
        if row.calculation_mode == "rate":
            low, central, high = row.rate_low, row.rate_central, row.rate_high
            mode = CostMode.RATE
        else:
            low, central, high = (
                row.amount_low_eur,
                row.amount_central_eur,
                row.amount_high_eur,
            )
            mode = CostMode.FIXED

        if central is None:
            continue

        costs.append(
            Cost(
                label=row.kind,
                mode=mode,
                phase=CostPhase(row.phase),
                low=low if low is not None else central,
                central=central,
                high=high if high is not None else central,
            )
        )
    return tuple(costs)


def _record(
    watch: Watch,
    reference: WatchReference | None,
    seller: Seller | None,
    has_platform: bool,
    price_eur: Decimal | None,
    ruleset: Ruleset,
) -> RecordCompleteness:
    raw = watch.raw_input
    condition = watch.condition_data

    return record_completeness(
        {
            "brand": reference is not None and bool(reference.brand),
            "reference": reference is not None and bool(reference.reference),
            "reference_status": watch.reference_status in ("confirmed", "corrected"),
            "mechanical_condition": condition.get("mechanical")
            not in (None, "unknown"),
            "cosmetic_condition": condition.get("cosmetic") not in (None, "unknown"),
            "originality": condition.get("originality") not in (None, "uncertain"),
            "box": raw.get("box") is not None,
            "papers": raw.get("papers") is not None,
            "price": price_eur is not None,
            "seller_country": seller is not None and seller.country_code is not None,
            "seller_type": seller is not None
            and seller.seller_type not in (None, "unknown"),
            # Un achat de particulier à particulier n'a pas de plateforme à
            # renseigner : le champ est sans objet, pas manquant. Le distinguer
            # d'un oubli évite de pénaliser un dossier complet.
            "platform": True if has_platform else None,
        },
        ruleset,
    )


async def _rule_for_platform(
    session: AsyncSession, platform_id: uuid.UUID, at: datetime
) -> PlatformRule | None:
    return (
        await session.execute(
            select(PlatformRule)
            .where(
                PlatformRule.platform_id == platform_id,
                PlatformRule.valid_from <= at,
                or_(PlatformRule.valid_to.is_(None), PlatformRule.valid_to > at),
            )
            .order_by(PlatformRule.region_code.desc(), PlatformRule.valid_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _fees(rule: PlatformRule) -> PlatformFees:
    return PlatformFees(
        buyer_fee_rate=rule.buyer_fee_rate,
        buyer_fee_fixed=rule.buyer_fee_fixed,
        buyer_fee_min=rule.buyer_fee_min,
        buyer_fee_max=rule.buyer_fee_max,
        seller_fee_rate=rule.seller_fee_rate,
        seller_fee_fixed=rule.seller_fee_fixed,
        seller_fee_min=rule.seller_fee_min,
        seller_fee_max=rule.seller_fee_max,
    )


async def _purchase_side(
    session: AsyncSession,
    listing: Listing | None,
    declared_platform_id: uuid.UUID | None,
    at: datetime,
) -> tuple[PlatformFees, uuid.UUID | None, str]:
    """Frais d'achat : ceux de la plateforme où l'on achète.

    Elle vient de l'annonce quand il y en a une, sinon de ce que l'utilisateur
    a déclaré sur la saisie manuelle. Faute des deux, l'achat est bien de
    particulier à particulier et ne coûte aucune commission — c'est un constat,
    pas une lacune.
    """

    platform_id = listing.platform_id if listing is not None else declared_platform_id
    if platform_id is None:
        return PlatformFees(), None, "Achat hors plateforme"

    rule = await _rule_for_platform(session, platform_id, at)
    if rule is None:
        # Rester muet ferait passer une plateforme à 20 % de commission pour
        # une plateforme gratuite : mieux vaut refuser l'analyse.
        raise DomainError(
            ErrorCode.NOT_FOUND,
            "Aucune règle de frais applicable pour la plateforme d'achat : "
            "les coûts d'achat ne peuvent pas être établis.",
        )
    return _fees(rule), rule.id, f"Achat — grille v{rule.version}"


async def _resale_side(
    session: AsyncSession, strategy_version: StrategyVersion, at: datetime
) -> tuple[PlatformFees, str]:
    """Frais de revente : ceux de la plateforme choisie par la stratégie.

    Où l'on revend est une décision, pas une propriété de l'annonce achetée.
    Reprendre la plateforme d'achat reviendrait à supposer une revente au même
    endroit — faux dès qu'on achète en enchère pour revendre en vitrine, et
    faux dans les deux sens puisque les commissions diffèrent.
    """

    code = strategy_version.settings.get(RESALE_PLATFORM)
    if code is None:
        return PlatformFees(), "Revente hors plateforme"

    platform = (
        await session.execute(select(Platform).where(Platform.code == str(code)))
    ).scalar_one_or_none()
    if platform is None:
        raise DomainError(
            ErrorCode.NOT_FOUND,
            f"La plateforme de revente de la stratégie est inconnue : {code}.",
        )

    rule = await _rule_for_platform(session, platform.id, at)
    if rule is None:
        raise DomainError(
            ErrorCode.NOT_FOUND,
            f"Aucune grille de frais pour {platform.name}, plateforme de "
            "revente de la stratégie : le produit net ne peut pas être établi.",
        )
    return _fees(rule), f"Revente {platform.name} — grille v{rule.version}"


async def run_analysis(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    settings: Settings,
) -> Analysis:
    """Calcule une analyse et la fige avec sa trace complète.

    Une analyse est immuable : un recalcul crée une nouvelle version chaînée à
    la précédente plutôt que de l'écraser (CLAUDE.md règle 4). Le barème, la
    stratégie et la position de portefeuille sont figés dans l'analyse, faute
    de quoi elle cesserait d'être rejouable dès le premier ajustement.
    """

    opportunity, watch, reference, seller, price_input = await get_opportunity(
        session, principal, opportunity_id
    )

    if price_input is None or price_input.amount_eur is None:
        # Un relevé sans montant en euros existe — une enchère sans offre, par
        # exemple. Il documente l'annonce, il ne suffit pas à l'évaluer.
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Aucun prix relevé en euros : l'analyse n'a rien à évaluer.",
        )
    price_eur = price_input.amount_eur

    valuation = (
        await session.execute(
            select(MarketValuation)
            .where(MarketValuation.opportunity_id == opportunity.id)
            .order_by(MarketValuation.calculated_at.desc(), MarketValuation.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if valuation is None:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Aucune cote de marché : calculez la valorisation avant d'analyser.",
        )

    ruleset = await load_ruleset(session, settings.active_ruleset_version)
    ruleset_id = (
        await session.execute(
            select(RulesetRow.id).where(
                RulesetRow.version == settings.active_ruleset_version
            )
        )
    ).scalar_one()

    strategy_version = await active_strategy_version(
        session, opportunity.portfolio_id, ruleset_id, principal.user_id
    )

    listing = None
    if opportunity.listing_id is not None:
        listing = (
            await session.execute(
                select(Listing).where(Listing.id == opportunity.listing_id)
            )
        ).scalar_one_or_none()

    now = datetime.now(UTC)
    purchase_fees, platform_rule_id, purchase_label = await _purchase_side(
        session, listing, opportunity.purchase_platform_id, now
    )
    resale_fees, resale_label = await _resale_side(session, strategy_version, now)

    cost_rows = list(
        (
            await session.execute(
                select(OpportunityCost).where(
                    OpportunityCost.opportunity_id == opportunity.id,
                    OpportunityCost.analysis_id.is_(None),
                )
            )
        ).scalars()
    )

    position = await current_position(
        session,
        opportunity.portfolio_id,
        brand=reference.brand if reference is not None else None,
    )

    record = _record(
        watch,
        reference,
        seller,
        has_platform=listing is not None
        or opportunity.purchase_platform_id is not None,
        price_eur=price_eur,
        ruleset=ruleset,
    )
    risk_level, reliability, protections, country = _seller_facts(seller)
    condition = watch.condition_data

    counts = await _comparable_counts(session, valuation.id)

    outcome = analyse(
        purchase_price_eur=price_eur,
        watch=WatchFacts(
            reference_status=watch.reference_status,
            identification_confidence=watch.identification_confidence,
            mechanical=str(condition.get("mechanical", "unknown")),
            cosmetic=str(condition.get("cosmetic", "unknown")),
            completeness=str(watch.completeness_data.get("level", "watch_only")),
            originality=str(condition.get("originality", "uncertain")),
            seller_country=country,
            seller_risk_level=risk_level,
            seller_reliability=reliability,
            transaction_protections=protections,
        ),
        market=MarketFacts(
            low_eur=valuation.low_value_eur,
            central_eur=valuation.central_value_eur,
            high_eur=valuation.high_value_eur,
            valuation_confidence=valuation.valuation_confidence,
            comparable_count=counts.used,
            total_weight=counts.total_weight,
            active_comparable_depth=counts.used,
            dispersion_subscore=_dispersion(valuation),
            dated_comparables=counts.dated,
        ),
        terms=StrategyTerms(
            minimum_roi=strategy_version.minimum_roi,
            minimum_profit_eur=strategy_version.minimum_profit_eur,
            maximum_allocation_rate=strategy_version.maximum_allocation_rate,
            negotiation_buffer=strategy_version.negotiation_buffer,
        ),
        position=position,
        transaction_costs=TransactionCosts(
            purchase_fees=purchase_fees,
            purchase_label=purchase_label,
            resale_fees=resale_fees,
            resale_label=resale_label,
            operational=_operational_costs(cost_rows),
        ),
        listing_quality_score=record.score,
        ruleset=ruleset,
    )

    previous = (
        await session.execute(
            select(Analysis.id)
            .where(Analysis.opportunity_id == opportunity.id)
            .order_by(Analysis.calculated_at.desc(), Analysis.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    analysis = _to_row(
        opportunity_id=opportunity.id,
        portfolio_id=opportunity.portfolio_id,
        valuation_id=valuation.id,
        previous_analysis_id=previous,
        ruleset_id=ruleset_id,
        strategy_version=strategy_version,
        platform_rule_id=platform_rule_id,
        price_eur=price_eur,
        outcome=outcome,
        record=record,
        position_snapshot={
            "available_cash_eur": str(position.available_cash_eur),
            "stock_at_cost_eur": str(position.stock_at_cost_eur),
            "brand_exposure_at_cost_eur": str(position.brand_exposure_at_cost_eur),
            "brand": reference.brand if reference is not None else None,
            "allocation_rate": str(outcome.allocation_rate),
            "brand_concentration_rate": str(outcome.brand_concentration_rate),
            "capital_immobilization_rate": str(outcome.capital_immobilization_rate),
        },
        ruleset_raw=ruleset.raw_config,
    )

    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)
    return analysis


def _to_row(
    *,
    opportunity_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    valuation_id: uuid.UUID,
    previous_analysis_id: uuid.UUID | None,
    ruleset_id: uuid.UUID,
    strategy_version: StrategyVersion,
    platform_rule_id: uuid.UUID | None,
    price_eur: Decimal,
    outcome: AnalysisOutcome,
    record: RecordCompleteness,
    position_snapshot: dict[str, object],
    ruleset_raw: str,
) -> Analysis:
    """Fige l'analyse et tout ce dont elle dépend.

    Les colonnes chiffrées ne sont renseignées que si l'analyse a pu aller au
    bout : le schéma refuse un score sans son prix, ses coûts et ses piliers,
    et il a raison — un score sans ses entrées n'est pas explicable.
    """

    central = outcome.scenarios[Scenario.CENTRAL]
    possible = outcome.gates.analysis_possible

    return Analysis(
        portfolio_id=portfolio_id,
        opportunity_id=opportunity_id,
        valuation_id=valuation_id,
        previous_analysis_id=previous_analysis_id,
        ruleset_id=ruleset_id,
        strategy_version_id=strategy_version.id,
        platform_rule_id=platform_rule_id,
        trigger_type="manual",
        # Publiée d'emblée, et non « brouillon ». Rien ne se passe entre le
        # calcul et l'affichage : aucune étape humaine ne vient compléter une
        # analyse. La laisser en brouillon la laisserait modifiable — le
        # déclencheur d'immuabilité ne protège que les analyses publiées —,
        # c'est-à-dire exactement l'inverse de la règle 4 pour le seul verdict
        # que l'utilisateur voit vraiment.
        state="published",
        published_at=datetime.now(UTC),
        current_price_eur=price_eur,
        total_cost_eur=central.total_cost_before_sale_eur if possible else None,
        expected_sale_price_eur=outcome.listing_price_eur if possible else None,
        raw_max_purchase_price_eur=outcome.max_purchase.raw_value_eur,
        max_purchase_price_eur=outcome.max_purchase.value_eur if possible else None,
        expected_profit_eur=central.net_profit_eur if possible else None,
        expected_roi=central.roi if possible else None,
        expected_days_to_sell=outcome.sale_delay.days,
        score=outcome.score.final_score if possible else None,
        evidence_quality_score=outcome.score.evidence_quality if possible else None,
        recommendation=outcome.score.verdict.value,
        gates=[
            {
                "code": result.code.value,
                "status": result.status.value,
                "reason_codes": list(result.reason_codes),
                "blocking": result.blocking,
            }
            for result in outcome.gates.results
        ],
        pillars=(
            {
                "profitability": str(outcome.score.profitability),
                "liquidity": str(outcome.score.liquidity),
                "portfolio": str(outcome.score.portfolio),
                "condition": str(outcome.score.condition),
                "evidence_quality": str(outcome.score.evidence_quality),
                "subscores": {
                    name: str(value) for name, value in outcome.score.subscores.items()
                },
            }
            if possible
            else None
        ),
        scenario_results=(
            {
                scenario.value: {
                    "sale_price_eur": str(result.sale_price_eur),
                    "total_cost_before_sale_eur": str(
                        result.total_cost_before_sale_eur
                    ),
                    "net_sale_proceeds_eur": str(result.net_sale_proceeds_eur),
                    "net_profit_eur": str(result.net_profit_eur),
                    "roi": None if result.roi is None else str(result.roi),
                    "roi_undefined_reason": result.roi_undefined_reason,
                }
                for scenario, result in outcome.scenarios.items()
            }
            if possible
            else None
        ),
        caps=[
            {"name": cap.name, "value": str(cap.value), "reason": cap.reason}
            for cap in outcome.score.applied_caps
        ],
        explanation={
            "ruleset_version": outcome.score.ruleset_version,
            "raw_score": str(outcome.score.raw_score),
            "blocking_conditions": list(outcome.score.blocking_conditions),
            "analysis_possible": possible,
            "max_purchase": {
                "value_eur": str(outcome.max_purchase.value_eur),
                "raw_value_eur": str(outcome.max_purchase.raw_value_eur),
                "increment_eur": str(outcome.max_purchase.increment_eur),
                "binding_constraint": outcome.max_purchase.binding_constraint,
                "solver": outcome.max_purchase.solver,
                "iterations": outcome.max_purchase.iterations,
            },
            "sale_delay": {
                "days": outcome.sale_delay.days,
                "base_days": outcome.sale_delay.base_days,
                "multiplier": str(outcome.sale_delay.multiplier),
                "depth_band": outcome.sale_delay.depth_band,
                "price_band": outcome.sale_delay.price_band,
                "thin_evidence": outcome.sale_delay.thin_evidence,
            },
            "record": {
                "score": str(record.score),
                "filled": list(record.filled),
                "missing": list(record.missing),
                "not_applicable": list(record.not_applicable),
            },
        },
        # Figé depuis le texte source : le barème conservé reste exactement
        # celui qui a produit le verdict, décimales comprises.
        ruleset_snapshot=cast(literal(ruleset_raw), JSONB),
        strategy_snapshot={
            "strategy_version_id": str(strategy_version.id),
            "version": strategy_version.version,
            "minimum_roi": str(strategy_version.minimum_roi),
            "minimum_profit_eur": str(strategy_version.minimum_profit_eur),
            "maximum_allocation_rate": str(strategy_version.maximum_allocation_rate),
            "negotiation_buffer": str(strategy_version.negotiation_buffer),
        },
        portfolio_snapshot=position_snapshot,
    )
