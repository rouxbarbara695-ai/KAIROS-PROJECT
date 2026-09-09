"""Du lien collé au formulaire prérempli.

Quatre étapes séparées, dans cet ordre, et chacune peut échouer sans annuler
les précédentes :

1. **reconnaître** la plateforme depuis l'URL, et décider si KAIROS a le droit
   d'aller la chercher ;
2. **récupérer** la page — ou constater le refus, et le dire précisément ;
3. **extraire** les champs des données structurées ;
4. **normaliser** ce qui peut l'être, en laissant absent ce qui manque.

La séparation n'est pas décorative. Elle permet à l'import assisté de
réemployer les étapes 3 et 4 sans toucher à la 2, et elle permet de tester
l'extraction sur des pages figées, sans réseau — sans quoi la suite dépendrait
d'annonces qui changent tous les jours.

**Une extraction partielle reste utile.** Un titre et un prix, c'est déjà
quatre champs de moins à saisir. L'échec complet lui-même conserve le lien :
l'utilisateur ne le recolle pas.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import structlog

from app.collection.adapters import catawiki_text, structured_data
from app.collection.application.access_policy import (
    AccessMode,
    access_for,
    allowed_hosts_for,
)
from app.collection.domain.fields import ListingDraft
from app.collection.ports.fetcher import FetchedPage, Fetcher
from app.platforms.application.detect_platform import detect_platform_code
from app.shared.domain.errors import DomainError, ErrorCode

_log = structlog.get_logger()

# Un contenu collé par l'utilisateur : assez large pour une page d'annonce
# complète, assez borné pour ne pas servir de dépôt.
MAX_PASTED_LENGTH = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PrefillOutcome:
    """Ce que la récupération a donné, y compris quand elle n'a rien donné.

    `draft` vaut `None` seulement si rien n'a pu être lu. Dans tous les cas
    `url` et `platform_code` sont renseignés : le formulaire garde le lien, et
    l'utilisateur n'a pas à le recoller.
    """

    url: str
    platform_code: str
    access_mode: AccessMode
    draft: ListingDraft | None
    #: `None` quand tout s'est bien passé.
    failure: dict[str, object] | None = None

    @property
    def succeeded(self) -> bool:
        return self.draft is not None


def _failure(
    url: str, platform_code: str, mode: AccessMode, error: DomainError
) -> PrefillOutcome:
    return PrefillOutcome(
        url=url,
        platform_code=platform_code,
        access_mode=mode,
        draft=None,
        failure={
            "code": error.code.value,
            "message": error.message,
            "details": error.details,
        },
    )


def _check_url(url: str) -> tuple[str, str]:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if not host or parts.scheme.lower() not in ("http", "https"):
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Ce n'est pas une adresse web valide.",
            field="url",
        )
    return host, detect_platform_code(url)


async def prefill_from_url(fetcher: Fetcher, url: str) -> PrefillOutcome:
    """Étape 1 à 4, à la demande de l'utilisateur, pour une seule annonce."""

    host, platform_code = _check_url(url)
    access = access_for(platform_code)

    if access.mode is not AccessMode.AUTOMATIC:
        # Ni requête, ni tentative : la décision se prend avant le réseau.
        _log.info(
            "prefill_not_attempted",
            platform=platform_code,
            mode=access.mode.value,
        )
        return PrefillOutcome(
            url=url,
            platform_code=platform_code,
            access_mode=access.mode,
            draft=None,
            failure={
                "code": ErrorCode.COLLECTOR_NOT_AUTHORIZED.value,
                "message": access.explanation,
                "details": {
                    "reason": (
                        "platform_forbids_automation"
                        if access.mode is AccessMode.FORBIDDEN
                        else "protected_by_platform"
                    ),
                    "fallback": (
                        "manual"
                        if access.mode is AccessMode.FORBIDDEN
                        else "assisted_import"
                    ),
                },
            },
        )

    try:
        page = await fetcher.fetch(url, allowed_hosts_for(platform_code, host))
    except DomainError as error:
        _log.info(
            "prefill_failed",
            platform=platform_code,
            code=error.code.value,
            reason=error.details.get("reason"),
        )
        return _failure(url, platform_code, access.mode, error)

    draft = structured_data.extract(page, platform_code)
    _log.info(
        "prefill_succeeded",
        platform=platform_code,
        filled=draft.filled_count,
        warnings=len(draft.warnings),
    )
    return PrefillOutcome(
        url=url,
        platform_code=platform_code,
        access_mode=access.mode,
        draft=draft,
    )


def prefill_from_content(url: str, content: str) -> PrefillOutcome:
    """Import assisté : l'utilisateur fournit lui-même la page.

    Le traitement est le même que pour une page récupérée — mêmes extracteurs,
    mêmes règles de normalisation — mais la **provenance** de chaque champ est
    `assisted`. C'est la seule chose qui compte ici : un champ obtenu ainsi ne
    doit jamais pouvoir passer pour le résultat d'une récupération automatique
    réussie, parce que la responsabilité de ce qui a été collé n'est pas la
    même.

    Rien de ce contenu n'est traité comme une consigne, et la page elle-même
    n'est pas conservée (Q-08).
    """

    host, platform_code = _check_url(url)
    del host

    if len(content) > MAX_PASTED_LENGTH:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Le contenu collé dépasse la taille acceptée.",
            field="content",
        )

    if not content.strip():
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            "Aucun contenu à analyser.",
            field="content",
        )

    # Catawiki a son propre lecteur, et il ne lit pas la même chose. Le
    # copier-coller du **texte visible** ne contient aucun `schema.org` : il
    # n'y a que des étiquettes et des valeurs. Exiger le code source de la
    # page pour retomber sur l'extracteur générique reviendrait à demander à
    # l'utilisateur d'ouvrir les outils de développement à chaque lot.
    if platform_code == catawiki_text.PLATFORM_CODE:
        draft = catawiki_text.extract(content, url)
    else:
        page = FetchedPage(
            final_url=url,
            status_code=200,
            content_type="text/html",
            text=content,
        )
        draft = structured_data.extract_assisted(page, platform_code)

    if draft.filled_count == 0:
        draft.warnings = (
            *draft.warnings,
            "Rien n'a pu être lu dans ce contenu. Il manque probablement la "
            "fiche produit structurée de la page : copier la page entière "
            "plutôt que le texte visible.",
        )

    _log.info(
        "prefill_assisted",
        platform=platform_code,
        filled=draft.filled_count,
    )
    return PrefillOutcome(
        url=url,
        platform_code=platform_code,
        access_mode=AccessMode.ASSISTED,
        draft=draft,
    )
