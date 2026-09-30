"""Une recherche de comparables, du déclenchement à l'estimation.

Le parcours : une montre à référence confirmée → recherche dans chaque source
configurée → contrôle d'identité annonce par annonce → déduplication →
enregistrement des comparables retenus avec leur provenance → **un seul**
recalcul de la cote et de l'analyse.

Rien ici ne décide d'une valeur : la cote reste le travail du moteur existant, et
les pondérations ne sont pas touchées. Ce module décide seulement quelles
annonces entrent dans ce moteur, et garde la preuve de chaque décision.

Une recherche est **visible pendant qu'elle tourne** : chaque source écrit son
résultat dès qu'elle a fini, de sorte que l'écran affiche des résultats partiels
et l'échec d'une source sans attendre les autres.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.comparables import ComparableCreate
from app.market.application.create_comparable import create_comparable
from app.market_search.application.runtime import SearchRuntime
from app.market_search.domain.candidate import (
    Candidate,
    SearchQuery,
    SourceOutcome,
)
from app.market_search.domain.dedupe import deduplicate
from app.market_search.domain.policy import SearchPolicy
from app.market_search.domain.screening import Verdict, screen
from app.market_search.ports.source import ComparableSource
from app.scoring.application.recalculate import (
    Recalculation,
    recalculate_after_comparable_change,
)
from app.shared.config import Settings
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.jobs import MarketSearchRun
from app.shared.infrastructure.db.models.market import Comparable
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.models.watches import Watch, WatchReference
from app.shared.infrastructure.fx import resolve_fx

logger = structlog.get_logger()

# Nom sous lequel les comparables issus de la source sont enregistrés. Il fait
# partie de l'identité unique (source, identifiant d'annonce, nature du prix).
SOURCE_LABELS = {"ebay": "eBay"}

# Une recherche « en cours » depuis plus longtemps a été interrompue (redémarrage
# du serveur) : sans ce délai, elle bloquerait toute nouvelle recherche.
_STALE_AFTER = timedelta(minutes=10)

_MAX_ACCEPTED_LISTED = 50
_MAX_REJECTED_EXAMPLES = 8

_BOX_AND_PAPERS = (
    "box and papers",
    "boite et papiers",
    "boîte et papiers",
    "full set",
    "fullset",
    "complete set",
    "coffret complet",
    "scatola e documenti",
    "box und papiere",
)


@dataclass(frozen=True, slots=True)
class StartResult:
    run: MarketSearchRun
    launched: bool
    #: `running` (déjà en cours), `fresh` (résultat encore frais) ou `too_soon`
    #: (actualisation trop rapprochée). `None` : une nouvelle recherche démarre.
    reused: str | None = None


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------
# Démarrage
# --------------------------------------------------------------------------


async def configured_source_names(
    runtime: SearchRuntime, settings: Settings
) -> list[str]:
    async with runtime.sources(settings, runtime.policy) as sources:
        return [source.name for source in sources if source.is_configured()]


async def start_search(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    settings: Settings,
    runtime: SearchRuntime,
    *,
    trigger: str,
    force: bool = False,
) -> StartResult:
    """Prépare une recherche ; ne la lance pas.

    Elle est **réutilisée** plutôt que doublée quand une recherche est déjà en
    cours, ou quand la précédente est encore fraîche : chaque requête coûte du
    quota à la source et n'apprend rien de neuf.
    """

    opportunity = (
        await session.execute(
            select(Opportunity).where(
                Opportunity.id == opportunity_id,
                Opportunity.portfolio_id.in_(principal.portfolio_ids),
            )
        )
    ).scalar_one_or_none()
    if opportunity is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Opportunité introuvable.")

    watch = (
        await session.execute(select(Watch).where(Watch.id == opportunity.watch_id))
    ).scalar_one()
    if watch.reference_id is None or watch.reference_status not in (
        "confirmed",
        "corrected",
    ):
        raise DomainError(
            ErrorCode.REFERENCE_UNCONFIRMED,
            "La référence doit être confirmée avant de chercher des comparables : "
            "une recherche sur une référence supposée ramènerait des montres "
            "qui ne sont pas la bonne.",
            field="reference_id",
        )

    if not await configured_source_names(runtime, settings):
        raise DomainError(
            ErrorCode.COLLECTOR_UNAVAILABLE,
            "Aucune source de recherche n'est configurée. Renseignez les "
            "identifiants eBay (EBAY_CLIENT_ID et EBAY_CLIENT_SECRET) pour "
            "activer la recherche automatique.",
            details={"sources": {"ebay": "not_configured"}},
        )

    portfolio_id = opportunity.portfolio_id
    reference_id = watch.reference_id
    now = _utcnow()
    policy = runtime.policy

    active = (
        await session.execute(
            select(MarketSearchRun).where(
                MarketSearchRun.portfolio_id == portfolio_id,
                MarketSearchRun.reference_id == reference_id,
                MarketSearchRun.status.in_(("queued", "running")),
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        if now - (active.started_at or active.created_at) > _STALE_AFTER:
            active.status = "failed"
            active.error_code = "STALE_RUN"
            active.error_message = "Recherche interrompue (redémarrage du serveur)."
            active.finished_at = now
            await session.commit()
        else:
            return StartResult(active, launched=False, reused="running")

    last = (
        await session.execute(
            select(MarketSearchRun)
            .where(
                MarketSearchRun.portfolio_id == portfolio_id,
                MarketSearchRun.reference_id == reference_id,
                MarketSearchRun.status.in_(("succeeded", "partial")),
            )
            .order_by(MarketSearchRun.finished_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is not None and last.finished_at is not None:
        age = now - last.finished_at
        if not force and age < timedelta(hours=policy.cache_ttl_hours):
            return StartResult(last, launched=False, reused="fresh")
        if force and age < timedelta(minutes=policy.min_refresh_minutes):
            return StartResult(last, launched=False, reused="too_soon")

    run = MarketSearchRun(
        portfolio_id=portfolio_id,
        opportunity_id=opportunity.id,
        reference_id=reference_id,
        requested_by_user_id=principal.user_id,
        trigger_kind=trigger,
        status="queued",
        policy_version=policy.version,
        sources=[],
        summary={"stage": "queued"},
    )
    session.add(run)
    try:
        await session.commit()
    except IntegrityError:
        # Deux demandes simultanées : l'index unique partiel a départagé.
        await session.rollback()
        existing = (
            await session.execute(
                select(MarketSearchRun).where(
                    MarketSearchRun.portfolio_id == portfolio_id,
                    MarketSearchRun.reference_id == reference_id,
                    MarketSearchRun.status.in_(("queued", "running")),
                )
            )
        ).scalar_one()
        return StartResult(existing, launched=False, reused="running")
    await session.refresh(run)
    return StartResult(run, launched=True)


# --------------------------------------------------------------------------
# Exécution (tâche de fond)
# --------------------------------------------------------------------------


async def execute_run(
    run_id: uuid.UUID, settings: Settings, runtime: SearchRuntime
) -> None:
    """Exécute une recherche préparée. Ne lève jamais : l'échec est écrit dans la
    recherche elle-même, où l'écran le lit."""

    factory = runtime.session_factory()
    async with factory() as session:
        run = await session.get(MarketSearchRun, run_id)
        if run is None or run.status != "queued":
            return
        principal = Principal(
            user_id=run.requested_by_user_id,
            portfolio_ids=frozenset({run.portfolio_id}),
        )
        opportunity_id = run.opportunity_id
        reference_id = run.reference_id
        started = _utcnow()
        run.status = "running"
        run.started_at = started
        run.summary = {"stage": "searching"}
        await session.commit()

        try:
            await _execute(
                session,
                run_id,
                principal,
                opportunity_id,
                reference_id,
                settings,
                runtime,
                started,
            )
        except Exception as error:  # noqa: BLE001 — jamais d'exception hors de la tâche
            # Le type suffit : une exception SQLAlchemy embarque ses paramètres,
            # et les journaliser pourrait écrire un numéro de série (règle 11).
            logger.error(
                "market_search_failed",
                error_type=type(error).__name__,
                run_id=str(run_id),
            )
            await session.rollback()
            failed = await session.get(MarketSearchRun, run_id)
            if failed is not None:
                failed.status = "failed"
                failed.error_code = "INTERNAL_ERROR"
                failed.error_message = (
                    "La recherche a échoué de façon inattendue. Aucun comparable "
                    "existant n'a été modifié."
                )
                failed.finished_at = _utcnow()
                await session.commit()


async def _execute(
    session: AsyncSession,
    run_id: uuid.UUID,
    principal: Principal,
    opportunity_id: uuid.UUID,
    reference_id: uuid.UUID,
    settings: Settings,
    runtime: SearchRuntime,
    started: datetime,
) -> None:
    policy = runtime.policy
    reference = (
        await session.execute(
            select(WatchReference).where(WatchReference.id == reference_id)
        )
    ).scalar_one()
    query = SearchQuery(
        brand=reference.brand, reference=reference.reference, model=reference.model
    )

    results: list[dict[str, Any]] = []
    recorded_by_kind: Counter[str] = Counter()
    total_recorded = 0

    used_today = await _requests_last_24h(session)

    async with runtime.sources(settings, policy) as sources:
        for source in sources:
            if not source.is_configured():
                continue
            if used_today + policy.max_requests_per_run > policy.daily_request_limit:
                entry = _quota_entry(source.name, used_today, policy)
            else:
                entry, recorded = await _search_one_source(
                    session,
                    principal,
                    opportunity_id,
                    run_id,
                    source,
                    query,
                    settings,
                    policy,
                )
                used_today += entry["requests_count"]
                recorded_by_kind.update(recorded)
                total_recorded += sum(recorded.values())
            results.append(entry)
            # Résultat visible dès que la source a fini, pas à la fin de tout.
            run = await session.get(MarketSearchRun, run_id)
            assert run is not None
            run.sources = list(results)
            run.summary = {"stage": "searching", "comparables_recorded": total_recorded}
            await session.commit()

    run = await session.get(MarketSearchRun, run_id)
    assert run is not None
    run.summary = {**run.summary, "stage": "recalculating"}
    await session.commit()

    total_known = await _comparables_count(session, principal, reference_id)
    recalculation: Recalculation | None = None
    # Recalculer quand quelque chose a changé, ou quand il n'y a pas assez de
    # comparables pour dire pourquoi : sans nouveauté, un recalcul ne ferait que
    # ajouter une version identique à la chaîne.
    if total_recorded > 0 or total_known < 2:
        recalculation = await recalculate_after_comparable_change(
            session, principal, opportunity_id, settings
        )

    finished = _utcnow()
    run = await session.get(MarketSearchRun, run_id)
    assert run is not None
    statuses = [entry["status"] for entry in results]
    run.status = _overall_status(statuses)
    run.sources = list(results)
    run.finished_at = finished
    run.summary = _summary(
        results=results,
        recorded_by_kind=recorded_by_kind,
        total_recorded=total_recorded,
        total_known=total_known,
        recalculation=recalculation,
        elapsed_s=round((finished - started).total_seconds(), 1),
        observed_at=finished,
    )
    await session.commit()


def _overall_status(statuses: list[str]) -> str:
    if statuses and all(s == "ok" for s in statuses):
        return "succeeded"
    if any(s == "ok" for s in statuses):
        return "partial"
    # `budget_exhausted` avec des résultats est partiel ; sans, c'est un échec.
    return "failed"


def _summary(
    *,
    results: list[dict[str, Any]],
    recorded_by_kind: Counter[str],
    total_recorded: int,
    total_known: int,
    recalculation: Recalculation | None,
    elapsed_s: float,
    observed_at: datetime,
) -> dict[str, Any]:
    insufficient = (
        recalculation is not None
        and recalculation.status == "skipped"
        and recalculation.reason == "insufficient_comparables"
    )
    return {
        "stage": "done",
        "elapsed_s": elapsed_s,
        "observed_at": observed_at.isoformat(),
        "comparables_recorded": total_recorded,
        "comparables_known_for_reference": total_known,
        "recorded_by_price_kind": dict(recorded_by_kind),
        "insufficient_data": insufficient,
        "insufficient_data_message": (
            "Données insuffisantes : aucune estimation n'est produite. "
            "Aucune valeur n'est inventée."
            if insufficient
            else None
        ),
        # La nature des prix est dite à côté de l'estimation : ce sont des prix
        # demandés et des enchères en cours, jamais des ventes conclues.
        "price_nature_note": (
            "Prix demandés et enchères en cours observés : ce ne sont pas des "
            "ventes conclues."
        ),
        "recalculation": None
        if recalculation is None
        else {
            "status": recalculation.status,
            "reason": recalculation.reason,
            "detail": recalculation.detail,
            "valuation_id": (
                str(recalculation.valuation_id) if recalculation.valuation_id else None
            ),
            "analysis_id": (
                str(recalculation.analysis_id) if recalculation.analysis_id else None
            ),
        },
    }


def _quota_entry(name: str, used: int, policy: SearchPolicy) -> dict[str, Any]:
    now = _utcnow().isoformat()
    return {
        "source": name,
        "status": "budget_exhausted",
        "message": (
            f"Quota quotidien de prudence atteint ({used} requêtes sur "
            f"{policy.daily_request_limit}) : source non interrogée."
        ),
        "started_at": now,
        "finished_at": now,
        "elapsed_s": 0.0,
        "requests": [],
        "requests_count": 0,
        "read": 0,
        "accepted": 0,
        "recorded": 0,
        "already_known": 0,
        "duplicates": 0,
        "fx_unavailable": 0,
        "rejected": {},
        "rejected_examples": [],
        "recorded_items": [],
    }


async def _requests_last_24h(session: AsyncSession) -> int:
    since = _utcnow() - timedelta(hours=24)
    rows = (
        await session.execute(
            select(MarketSearchRun.sources).where(MarketSearchRun.created_at >= since)
        )
    ).scalars()
    return sum(
        int(entry.get("requests_count", 0) or 0)  # type: ignore[call-overload]
        for sources in rows
        for entry in sources
    )


async def _comparables_count(
    session: AsyncSession, principal: Principal, reference_id: uuid.UUID
) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(Comparable)
                .where(
                    Comparable.reference_id == reference_id,
                    Comparable.portfolio_id.in_(principal.portfolio_ids),
                )
            )
        ).scalar_one()
    )


def _box_and_papers(title: str) -> tuple[bool | None, bool | None]:
    """Boîte et papiers, seulement sur mention explicite : l'absence de mention
    n'est pas une absence de boîte."""

    lowered = title.lower()
    if any(marker in lowered for marker in _BOX_AND_PAPERS):
        return True, True
    return None, None


async def _search_one_source(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    run_id: uuid.UUID,
    source: ComparableSource,
    query: SearchQuery,
    settings: Settings,
    policy: SearchPolicy,
) -> tuple[dict[str, Any], Counter[str]]:
    started = _utcnow()
    outcome: SourceOutcome = await source.search(query)

    # La même annonce lue par deux requêtes (les deux écritures de la référence)
    # est une redite, pas deux annonces : elle n'est comptée qu'une fois.
    distinct: dict[tuple[str, str], Candidate] = {}
    for candidate in outcome.candidates:
        distinct.setdefault((candidate.external_id, candidate.price_kind), candidate)
    read = list(distinct.values())

    verdicts: list[tuple[Candidate, Verdict]] = [
        (
            candidate,
            screen(
                candidate,
                brand=query.brand,
                reference=query.reference,
                model=query.model,
                policy=policy,
                now=started,
            ),
        )
        for candidate in read
    ]
    rejected: Counter[str] = Counter(v.code for _, v in verdicts if not v.accepted)
    examples = [
        {"title": c.title[:140], "code": v.code, "detail": v.detail}
        for c, v in verdicts
        if not v.accepted
    ][:_MAX_REJECTED_EXAMPLES]

    accepted = [(c, v) for c, v in verdicts if v.accepted]
    verdict_by_id = {c.external_id: v for c, v in accepted}
    deduped = deduplicate([c for c, _ in accepted])

    label = SOURCE_LABELS.get(source.name, source.name)
    known_ids = await _known_external_ids(
        session, principal, label, [c.external_id for c in deduped.kept]
    )

    recorded: Counter[str] = Counter()
    recorded_items: list[dict[str, Any]] = []
    already_known = 0
    fx_unavailable = 0
    for candidate in deduped.kept:
        if (candidate.external_id, candidate.price_kind) in known_ids:
            already_known += 1
            continue
        try:
            comparable = await _record(
                session,
                principal,
                opportunity_id,
                run_id,
                label,
                candidate,
                verdict_by_id[candidate.external_id],
                query,
                settings,
                policy,
            )
        except DomainError as error:
            if error.code is ErrorCode.FX_RATE_UNAVAILABLE:
                fx_unavailable += 1
                continue
            raise
        except IntegrityError:
            # Course avec une autre recherche : le comparable existe déjà.
            await session.rollback()
            already_known += 1
            continue
        recorded[candidate.price_kind] += 1
        if len(recorded_items) < _MAX_ACCEPTED_LISTED:
            recorded_items.append(
                {
                    "comparable_id": str(comparable.id),
                    "title": candidate.title[:140],
                    "url": candidate.url,
                    "amount": str(candidate.amount),
                    "currency": candidate.currency,
                    "price_kind": candidate.price_kind,
                }
            )

    finished = _utcnow()
    entry: dict[str, Any] = {
        "source": source.name,
        "status": outcome.status,
        "message": outcome.message,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "elapsed_s": round((finished - started).total_seconds(), 1),
        "requests": [
            {
                "label": r.label,
                "http_status": r.http_status,
                "elapsed_s": r.elapsed_s,
                "note": r.note,
            }
            for r in outcome.requests
        ],
        "requests_count": len(outcome.requests),
        "read": len(read),
        "accepted": len(accepted),
        "recorded": sum(recorded.values()),
        "already_known": already_known,
        "duplicates": len(deduped.duplicates),
        "fx_unavailable": fx_unavailable,
        "rejected": dict(rejected),
        "rejected_examples": examples,
        "recorded_items": recorded_items,
    }
    return entry, recorded


async def _known_external_ids(
    session: AsyncSession,
    principal: Principal,
    source_label: str,
    external_ids: list[str],
) -> set[tuple[str, str]]:
    if not external_ids:
        return set()
    rows = await session.execute(
        select(Comparable.source_external_id, Comparable.price_kind).where(
            Comparable.portfolio_id.in_(principal.portfolio_ids),
            Comparable.source_name == source_label,
            Comparable.source_external_id.in_(external_ids),
        )
    )
    return {(str(external), str(kind)) for external, kind in rows}


async def _record(
    session: AsyncSession,
    principal: Principal,
    opportunity_id: uuid.UUID,
    run_id: uuid.UUID,
    source_label: str,
    candidate: Candidate,
    verdict: Verdict,
    query: SearchQuery,
    settings: Settings,
    policy: SearchPolicy,
) -> Comparable:
    fx = await resolve_fx(session, candidate.currency, settings.fx_max_age_hours)
    if fx is None:
        raise DomainError(
            ErrorCode.FX_RATE_UNAVAILABLE,
            f"Aucun taux {candidate.currency}→EUR suffisamment récent.",
            field="currency",
        )

    # Les frais de port ne sont repris que dans la devise du prix : les convertir
    # avec un autre taux serait deviner.
    shipping_eur = (
        fx.convert(candidate.shipping_amount)
        if candidate.shipping_amount is not None
        and candidate.shipping_currency == candidate.currency
        else None
    )

    box, papers = _box_and_papers(candidate.title)
    payload = ComparableCreate(
        source_name=source_label,
        source_external_id=candidate.external_id,
        # Jamais de pseudonyme de vendeur : donnée personnelle (règle de licence
        # de l'API), et la cote n'en a pas besoin.
        seller_fingerprint=None,
        price_kind=candidate.price_kind,
        amount=candidate.amount,
        currency=candidate.currency,
        compulsory_shipping_eur=shipping_eur,
        market_status="active",
        listed_at=candidate.listed_at,
        observed_at=candidate.observed_at,
        # Annonce active observée : classe C. Jamais A ni B, qui exigent une
        # vente ou un résultat public confirmé.
        source_reliability="c",
        box=box,
        papers=papers,
    )
    provenance: dict[str, object] = {
        "origin": "automatic_search",
        "run_id": str(run_id),
        "policy_version": policy.version,
        "source": candidate.source,
        "marketplace": candidate.marketplace,
        "title": candidate.title,
        "url": candidate.url,
        "external_id": candidate.external_id,
        "identity": {
            "brand": query.brand,
            "reference": query.reference,
            "verdict": verdict.code,
            "warnings": list(verdict.warnings),
        },
        "country": candidate.country,
        "condition_text": candidate.condition_text,
        "offers_accepted": candidate.offers_accepted,
        "bid_count": candidate.bid_count,
        "auction_ends_at": candidate.ends_at.isoformat() if candidate.ends_at else None,
        "shipping_included_in_total": shipping_eur is not None,
        "price_nature_note": (
            "Prix demandé observé sur une annonce active : pas une vente conclue."
            if candidate.price_kind == "asking"
            else "Enchère en cours : mise actuelle, pas un prix final."
        ),
    }
    return await create_comparable(
        session, principal, opportunity_id, payload, settings, provenance=provenance
    )
