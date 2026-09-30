"""Registre des sources : pour chacune, ce qui a été vérifié, et quand.

Une source n'est pas « autorisée » parce que sa page répond `200` ou que son
`robots.txt` laisse passer un chemin. Ce registre garde, par source : le mode
d'accès, les conditions lues (page, date, ce qu'elles disent), la preuve d'accès
réelle, la nature des prix, les limites de rythme — et **ce qui n'a pas pu être
vérifié**. Il est la référence de `docs/decisions/registre-sources.md`.

Statuts :

- `validated` : accès réel prouvé, mode officiel ou conditions sans exclusion ;
- `conditional` : accès réel prouvé, aucune exclusion trouvée, mais une part des
  conditions n'a pas pu être lue — à confirmer par le propriétaire ;
- `excluded` : le mode envisagé est exclu (clause, protection) — jamais activé.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["validated", "conditional", "excluded"]


@dataclass(frozen=True, slots=True)
class SourceInfo:
    code: str
    label: str
    status: Status
    mode: str
    role: Literal["encheres", "revente", "les_deux"]
    price_nature: str
    currency: str
    country: str
    conditions_url: str | None
    checked_on: str
    conditions_note: str
    access_proof: str
    pace: str
    enabled: bool = True


SOURCES: dict[str, SourceInfo] = {
    "ebay": SourceInfo(
        code="ebay",
        label="eBay",
        status="validated",
        mode="API officielle Browse (programme développeur gratuit)",
        role="revente",
        price_nature="prix demandés et enchères en cours",
        currency="EUR (places de marché FR, DE, IT)",
        country="—",
        conditions_url="https://go.developer.ebay.com/api-license-agreement",
        checked_on="2026-09-30",
        conditions_note=(
            "Contrat de licence de l'API lu : pas de donnée personnelle conservée, "
            "âge des annonces affiché, aucune information de réserve, aucune "
            "statistique de catégorie."
        ),
        access_proof=(
            "Jeton OAuth joignable (401 sur de faux identifiants, diagnostic "
            "exact). Recherche réelle : en attente des identifiants."
        ),
        pace=(
            "5 000 appels/jour ; 12 requêtes par recherche ; plafond de prudence 4 000"
        ),
    ),
    "phigora": SourceInfo(
        code="phigora",
        label="Phigora",
        status="conditional",
        mode="Catalogue UCP (protocole publié par la boutique pour les agents)",
        role="revente",
        price_nature="prix demandés ; « Sold » = dernier prix affiché, pas une vente",
        currency="USD",
        country="US",
        conditions_url="https://www.phigora.com/policies/terms-of-service",
        checked_on="2026-09-30",
        conditions_note=(
            "Conditions non lues : la page est protégée par un défi anti-robot depuis "
            "l'environnement de développement (HTTP 429). Le canal UCP est, lui, "
            "publié par la boutique pour les agents et joignable."
        ),
        access_proof=(
            "search_catalog réel : Omega 1561.61.00 trouvée (1 exacte), Speedmaster "
            "3570.50.00 (3 exactes), 10 résultats par appel, ~1 s."
        ),
        pace="1 s entre deux appels ; 3 pages au plus",
    ),
    "antiquorum": SourceInfo(
        code="antiquorum",
        label="Antiquorum",
        status="conditional",
        mode="Pages publiques du catalogue en ligne (/en/lots)",
        role="encheres",
        price_nature="résultats d'adjudication publiés ; frais acheteur inconnus",
        currency="CHF, HKD, USD, EUR selon la vente",
        country="CH",
        conditions_url=(
            "https://www.antiquorum.swiss/condition-of-sales/geneva/"
            "conditions-of-sale/conditions-of-sales-for-geneva/"
        ),
        checked_on="2026-09-30",
        conditions_note=(
            "Conditions de vente (Genève) lues : aucune clause sur l'accès "
            "automatisé ; conditions d'utilisation du site non localisées. "
            "robots.txt autorise /en/lots/ ; plan du site annoncé mais en 404."
        ),
        access_proof=(
            "Recherche « Reverso Duetto » : 19 lots, 3 portent la référence "
            "266.1.44 (adjudications 2009, 2013, 2025)."
        ),
        pace="5 s entre deux requêtes ; 3 pages de 20 lots au plus",
    ),
    "sworders": SourceInfo(
        code="sworders",
        label="Sworders",
        status="conditional",
        mode="Pages publiques de l'archive des lots (/auction/search)",
        role="encheres",
        price_nature="résultats d'adjudication publiés ; frais acheteur inconnus",
        currency="GBP",
        country="GB",
        conditions_url="https://www.sworder.co.uk/terms-and-conditions-specialist",
        checked_on="2026-09-30",
        conditions_note=(
            "Conditions de vente (spécialistes) lues : aucune clause sur l'accès "
            "automatisé ; commission acheteur 25 % avant le 1er juillet 2026, "
            "27 % ensuite (première tranche). robots.txt : crawl-delay 10 s."
        ),
        access_proof=(
            "Recherche « Reverso Duetto » : lot 290 (18 nov. 2025), référence "
            "266.1.44 lue sur la fiche, adjugé 3 500 £."
        ),
        pace="10 s entre deux requêtes (crawl-delay) ; 8 fiches au plus",
    ),
    "vintage_watch_agency": SourceInfo(
        code="vintage_watch_agency",
        label="Vintage Watch Agency",
        status="conditional",
        mode="Pages publiques (/search-results.html)",
        role="revente",
        price_nature="prix demandés d'un marchand, en stock",
        currency="EUR",
        country="SE",
        conditions_url="https://www.vintagewatchagency.com/conditions.html",
        checked_on="2026-09-30",
        conditions_note=(
            "Page « Terms of Use & Privacy Policy » : aucun texte rendu à un client "
            "sans navigateur — conditions NON LUES. robots.txt n'exclut que "
            "/reviews.html."
        ),
        access_proof=(
            "Recherche « 1561.61.00 » : 1 fiche exacte, 1 520 € (1 610 € avant "
            "remise), en stock, état 4/5, boîte d'origine."
        ),
        pace="3 s entre deux requêtes",
    ),
    "catawiki": SourceInfo(
        code="catawiki",
        label="Catawiki",
        status="excluded",
        mode="Lecture automatisée de pages : exclue",
        role="encheres",
        price_nature="—",
        currency="—",
        country="NL",
        conditions_url=(
            "https://cdn.catawiki.net/assets/marketing/terms/2026/web/"
            "general-terms/general-terms-en-092026.pdf"
        ),
        checked_on="2026-09-30",
        conditions_note=(
            "Conditions générales (en vigueur au 15/09/2026), « Respect "
            "intellectual property » : « Scraping our website is not allowed. We "
            "may take any measures available to us under applicable law to prevent "
            "or address scraping. »"
        ),
        access_proof="Pages lisibles, plan des lots clos existant : non utilisés.",
        pace="—",
        enabled=False,
    ),
    "chrono24": SourceInfo(
        code="chrono24",
        label="Chrono24",
        status="excluded",
        mode="Accès direct automatisé : exclu",
        role="revente",
        price_nature="—",
        currency="—",
        country="DE",
        conditions_url="https://www.chrono24.fr/info/agb.htm",
        checked_on="2026-09-30",
        conditions_note=(
            "Défi anti-robot (Cloudflare, HTTP 403) sur la recherche et sur les "
            "conditions elles-mêmes ; les articles 6.2 et 6.3 des conditions "
            "restreignent la recherche automatisée (rapporté, non relu depuis "
            "l'environnement de développement)."
        ),
        access_proof="Bloqué : jamais contourné.",
        pace="—",
        enabled=False,
    ),
}


def label_of(code: str) -> str:
    info = SOURCES.get(code)
    return info.label if info else code
