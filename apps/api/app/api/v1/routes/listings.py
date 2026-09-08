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

from fastapi import APIRouter, Depends

from app.api.v1.schemas.listings import (
    AssistedPrefillRequest,
    ImportedFieldResponse,
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
