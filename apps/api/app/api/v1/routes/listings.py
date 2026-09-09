"""Préremplir une opportunité depuis un lien.

Deux routes, et la seconde existe parce que la première échoue légitimement :

- `POST /listings/prefill` — KAIROS va chercher la page. N'est tenté que là où
  la plateforme le permet (`docs/decisions/open-questions.md`, Q-04/05/06).
- `POST /listings/prefill/assisted` — l'utilisateur fournit le contenu.
  Traitement identique, provenance différente.

**Aucune des deux n'écrit en base.** Elles rendent un brouillon ; c'est
`POST /opportunities` qui crée quelque chose, une fois que l'utilisateur a
vérifié. Un préremplissage abandonné ne doit rien laisser derrière lui, et un
utilisateur qui recolle un lien ne doit pas se voir refuser un doublon qu'il
n'a jamais créé.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.listings import (
    AssistedPrefillRequest,
    ImportedFieldResponse,
    ImportTracePage,
    ImportTraceResponse,
    ListingPrefillResponse,
    PlatformAccessResponse,
    PrefillFailureResponse,
    PrefillRequest,
)
from app.collection.adapters.http_fetcher import HttpFetcher
from app.collection.application.access_policy import access_for
from app.collection.application.prefill import (
    PrefillOutcome,
    prefill_from_content,
    prefill_from_url,
)
from app.collection.ports.fetcher import Fetcher
from app.platforms.application.detect_platform import detect_platform_code
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.listings import ListingObservation
from app.shared.infrastructure.db.models.opportunities import Opportunity
from app.shared.infrastructure.db.session import get_session
from app.shared.infrastructure.portfolio_lookup import portfolio_of_opportunity
from app.shared.infrastructure.principal_provider import get_current_principal

router = APIRouter(tags=["listings"])


def get_fetcher() -> Fetcher:
    return HttpFetcher()


def _to_response(outcome: PrefillOutcome) -> ListingPrefillResponse:
    draft = outcome.draft
    return ListingPrefillResponse(
        url=outcome.url,
        platform_code=outcome.platform_code,
        access_mode=outcome.access_mode.value,
        succeeded=outcome.succeeded,
        canonical_url=draft.canonical_url if draft else None,
        fetched_at=draft.fetched_at if draft else None,
        fields=(
            {
                name: ImportedFieldResponse(**field.to_json())
                for name, field in draft.fields().items()
            }
            if draft
            else {}
        ),
        photos=list(draft.photos) if draft else [],
        warnings=list(draft.warnings) if draft else [],
        failure=(
            PrefillFailureResponse(**outcome.failure) if outcome.failure else None
        ),
    )


@router.post("/listings/prefill", response_model=ListingPrefillResponse)
async def prefill_listing_route(
    body: PrefillRequest,
    principal: Principal = Depends(get_current_principal),
    fetcher: Fetcher = Depends(get_fetcher),
) -> ListingPrefillResponse:
    """Récupère une annonce, à la demande, et rend un brouillon à vérifier.

    Rend `200` même en cas d'échec de récupération : ce n'est pas une erreur de
    la requête, c'est un résultat. Le corps porte `succeeded: false` et dit
    précisément ce qui a bloqué, pour que l'interface propose le bon repli
    plutôt qu'un message générique.
    """

    del principal  # authentification requise, portefeuille non impliqué
    return _to_response(await prefill_from_url(fetcher, body.url))


@router.post("/listings/prefill/assisted", response_model=ListingPrefillResponse)
async def prefill_listing_from_content_route(
    body: AssistedPrefillRequest,
    principal: Principal = Depends(get_current_principal),
) -> ListingPrefillResponse:
    """Analyse un contenu fourni par l'utilisateur.

    Aucune requête sortante n'est émise : c'est tout l'intérêt du repli là où
    la plateforme refuse les accès automatisés. Le contenu est traité comme une
    donnée, jamais comme une consigne, et n'est pas conservé (Q-08).
    """

    del principal
    return _to_response(prefill_from_content(body.url, body.content))


@router.get("/listings/access", response_model=PlatformAccessResponse)
async def platform_access_route(
    url: str,
    principal: Principal = Depends(get_current_principal),
) -> PlatformAccessResponse:
    """Dit, avant toute tentative, ce que KAIROS pourra faire de ce lien.

    Permet à l'interface d'annoncer « cette plateforme demande un import
    assisté » au moment où le lien est collé, plutôt que de faire attendre
    l'utilisateur pour un refus prévisible.
    """

    del principal
    code = detect_platform_code(url)
    access = access_for(code)
    return PlatformAccessResponse(
        platform_code=code,
        access_mode=access.mode.value,
        explanation=access.explanation,
    )


@router.get("/opportunities/{opportunity_id}/import", response_model=ImportTracePage)
async def opportunity_import_trace_route(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> ImportTracePage:
    """Ce que l'annonce affichait quand le dossier a été créé.

    C'est la moitié manquante du parcours : sans elle, un dossier rouvert six
    semaines plus tard ne dit plus quelle valeur venait de l'annonce et
    laquelle a été corrigée à la main. Les observations sont rendues de la
    plus récente à la plus ancienne — une seconde récupération en ajoute une,
    elle n'écrase rien.
    """

    await portfolio_of_opportunity(session, principal, opportunity_id)

    observations = (
        (
            await session.execute(
                select(ListingObservation)
                .join(
                    Opportunity,
                    Opportunity.listing_id == ListingObservation.listing_id,
                )
                .where(Opportunity.id == opportunity_id)
                .order_by(ListingObservation.observed_at.desc())
            )
        )
        .scalars()
        .all()
    )

    items = []
    for observation in observations:
        raw = observation.raw_data or {}
        fields = raw.get("fields") or {}
        items.append(
            ImportTraceResponse(
                observed_at=observation.observed_at.isoformat(),
                platform_code=_as_text(raw.get("platform_code")),
                access_mode=_as_text(raw.get("access_mode")),
                fetch_status=observation.fetch_status,
                reserve_met=observation.reserve_met,
                auction_end_at=(
                    observation.auction_end_at.isoformat()
                    if observation.auction_end_at
                    else None
                ),
                fields=(
                    {
                        name: ImportedFieldResponse(**value)
                        for name, value in fields.items()
                        if isinstance(value, dict)
                    }
                    if isinstance(fields, dict)
                    else {}
                ),
                warnings=_as_warnings(raw.get("warnings")),
            )
        )

    return ImportTracePage(items=items)


def _as_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_warnings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
