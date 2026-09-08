"""Formes échangées pour le préremplissage depuis un lien.

Une remarque sur `ImportedFieldResponse` : chaque champ est un objet, jamais
une valeur nue. C'est plus verbeux, et c'est le but — l'interface doit pouvoir
afficher « importé », « fourni par vous » ou « non renseigné » à côté de chaque
case, et un champ absent doit se distinguer d'un champ vide. Aplatir la
réponse ferait perdre exactement l'information qui rend le préremplissage sûr.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PrefillRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class AssistedPrefillRequest(BaseModel):
    """Repli : l'utilisateur fournit lui-même le contenu de la page.

    `url` reste obligatoire — c'est elle qui identifie l'annonce et qui
    reconnaît la plateforme. Le contenu ne la remplace pas, il la complète.
    """

    url: str = Field(min_length=8, max_length=2048)
    content: str = Field(min_length=1, max_length=4 * 1024 * 1024)


class ImportedFieldResponse(BaseModel):
    """Une valeur, ce qu'elle était avant normalisation, et d'où elle vient."""

    raw: str | None = None
    value: Any = None
    provenance: Literal["imported", "assisted", "user", "absent"]
    #: Où la valeur a été lue (`schema.org/Product.mpn`…), ou pourquoi elle
    #: manque. Sert à expliquer une valeur douteuse sans relire la page.
    source: str | None = None
    #: Lectures divergentes du même champ. Signalées, jamais arbitrées.
    conflicts: list[str] = Field(default_factory=list)


class PrefillFailureResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ListingPrefillResponse(BaseModel):
    """Ce que la récupération a donné — y compris quand elle n'a rien donné.

    `url` et `platform_code` sont toujours renseignés : en cas d'échec, le
    formulaire garde le lien et l'utilisateur n'a pas à le recoller.
    """

    url: str
    platform_code: str
    access_mode: Literal["automatic", "assisted", "forbidden"]
    succeeded: bool
    canonical_url: str | None = None
    fetched_at: str | None = None
    fields: dict[str, ImportedFieldResponse] = Field(default_factory=dict)
    photos: list[str] = Field(default_factory=list)
    #: Ce que l'extraction n'a pas su faire, dit en clair.
    warnings: list[str] = Field(default_factory=list)
    #: Renseigné seulement quand `succeeded` est faux.
    failure: PrefillFailureResponse | None = None


class PlatformAccessResponse(BaseModel):
    """Ce que KAIROS a le droit de faire sur une plateforme, et pourquoi."""

    platform_code: str
    access_mode: Literal["automatic", "assisted", "forbidden"]
    explanation: str


class ImportTraceResponse(BaseModel):
    """Ce que l'annonce affichait au moment de l'import.

    Rendue en rouvrant un dossier : c'est elle qui permet de dire, des
    semaines plus tard, quelle valeur venait de l'annonce et laquelle a été
    saisie à la main. Immuable — une seconde récupération ajoute une
    observation, elle n'écrase pas celle-ci.
    """

    observed_at: str
    platform_code: str | None = None
    access_mode: str | None = None
    fetch_status: str
    reserve_met: bool | None = None
    auction_end_at: str | None = None
    fields: dict[str, ImportedFieldResponse] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ImportTracePage(BaseModel):
    items: list[ImportTraceResponse] = Field(default_factory=list)
