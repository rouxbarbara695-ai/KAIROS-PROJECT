"""Ce qu'une source rend : des annonces candidates, jamais des comparables.

Un candidat n'est pas encore un comparable. Il ne le devient qu'après avoir passé
le contrôle d'identité et de configuration (`screening.py`) : tant que la
référence exacte n'est pas prouvée dans le texte de l'annonce, il reste un
voisin, et un voisin n'entre pas dans la cote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

PriceKind = Literal["asking", "current_bid", "hammer"]
MarketStatus = Literal["active", "sold", "ended", "unknown"]
FeesStatus = Literal["not_applicable", "included", "excluded", "unknown"]


@dataclass(frozen=True, slots=True)
class Candidate:
    """Une annonce active telle que la source la publie.

    Aucune donnée personnelle : ni pseudonyme de vendeur, ni note, ni adresse.
    Les conditions de l'API eBay l'exigent (données personnelles supprimées à la
    demande de l'utilisateur concerné), et la cote n'en a pas besoin.
    """

    source: str
    external_id: str
    title: str
    url: str
    amount: Decimal
    currency: str
    price_kind: PriceKind
    observed_at: datetime
    listed_at: datetime | None = None
    ends_at: datetime | None = None
    bid_count: int | None = None
    shipping_amount: Decimal | None = None
    shipping_currency: str | None = None
    country: str | None = None
    condition_text: str | None = None
    marketplace: str | None = None
    offers_accepted: bool = False
    #: Texte descriptif complet de l'annonce, **déjà nettoyé** (balises, numéros de
    #: série). Sert au contrôle d'identité quand le titre ne porte pas la
    #: référence (maisons de ventes) ; il n'est jamais conservé tel quel.
    description: str | None = None
    #: Statut affiché par la source. « sold » n'est utilisé que si la source le
    #: dit expressément : une disparition n'est jamais une vente.
    market_status: MarketStatus = "active"
    #: Date de la vente si la source la publie (adjudication).
    sold_at: datetime | None = None
    #: Les frais acheteur sont-ils dans le montant ? `unknown` tant que la source
    #: ne le dit pas : jamais normalisé en silence.
    fees_status: FeesStatus = "not_applicable"
    #: Lieu de la source (pays) : sépare marchés, devises et fiscalité.
    source_country: str | None = None


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Ce que KAIROS sait de la montre cherchée."""

    brand: str
    reference: str
    model: str | None = None


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """Une requête réellement émise : la preuve de ce qui a été interrogé."""

    label: str
    http_status: int | None
    elapsed_s: float
    note: str | None = None


SourceStatus = Literal[
    "ok",
    "not_configured",
    "blocked",
    "rate_limited",
    "budget_exhausted",
    "error",
]


@dataclass(slots=True)
class SourceOutcome:
    """Résultat d'une source : candidats, requêtes émises, et diagnostic exact.

    Un échec n'efface jamais des candidats valides déjà lus, et n'est jamais
    présenté comme une absence de résultat (CLAUDE.md règle 7).
    """

    source: str
    status: SourceStatus
    candidates: list[Candidate] = field(default_factory=list)
    requests: list[RequestRecord] = field(default_factory=list)
    message: str | None = None
    #: La recherche a-t-elle vu **tous** les résultats de la source ? `False`
    #: quand une limite (pages, requêtes) a coupé la lecture : l'absence d'une
    #: annonce n'est alors pas une preuve.
    complete: bool = True
