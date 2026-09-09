"""Extraction depuis les données structurées de la page.

**Pourquoi les données structurées et pas le texte.** Une annonce publie
souvent un bloc `schema.org/Product` en JSON-LD, destiné aux moteurs de
recherche : marque, référence, prix, devise, état, année y sont **étiquetés**
par le vendeur lui-même. Lire ces étiquettes, c'est recopier ce que le vendeur
a déclaré. Deviner les mêmes champs dans une phrase publicitaire, c'est
interpréter — et l'interprétation est précisément ce que la règle 1 interdit
d'inventer.

L'ordre de préférence est donc : JSON-LD, puis OpenGraph pour ce que le JSON-LD
n'a pas, puis rien. Il n'y a pas de troisième niveau qui devinerait dans le
texte libre : le texte n'est lu que pour deux choses explicitement bornées —
les mentions de boîte et de papiers, et la déclaration d'authenticité — et
chacune n'accepte que des formulations non ambiguës.

Aucun modèle de langage n'intervient. Ce serait justifiable pour interpréter
une description libre, mais pas ici : ce qu'il produirait sur un champ absent
serait une valeur plausible, c'est-à-dire exactement la faute que le lot doit
éviter. Le jour où ce sera utile, ce sera pour classer une phrase existante,
pas pour combler un vide.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.collection.domain import normalisation as norm
from app.collection.domain.fields import Imported, ListingDraft, Provenance, absent
from app.collection.domain.sanitize import clean_text, strip_serials
from app.collection.ports.fetcher import FetchedPage
from app.opportunities.domain.canonical_url import canonicalize_url

_JSON_LD_OPEN = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>",
    re.IGNORECASE,
)
_SCRIPT_CLOSE = re.compile(r"</script\s*>", re.IGNORECASE)
_META = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']([^\"']+)[\"'][^>]*content=[\"']([^\"']*)[\"']",
    re.IGNORECASE,
)
_META_REVERSED = re.compile(
    r"<meta[^>]+content=[\"']([^\"']*)[\"'][^>]*(?:property|name)=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)


def _json_ld_products(html: str) -> list[dict[str, Any]]:
    """Tous les objets `Product` du document, quel que soit leur emballage.

    Un site les publie tantôt seuls, tantôt dans un `@graph`, tantôt dans un
    tableau. Un bloc illisible est ignoré sans faire échouer le reste : une
    page mal formée quelque part ne doit pas coûter les champs qu'elle donne
    ailleurs.
    """

    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if any(isinstance(t, str) and t.lower() == "product" for t in types):
            found.append(node)
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                walk(node[key])

    for block in _json_ld_blocks(html):
        try:
            walk(json.loads(block))
        except (json.JSONDecodeError, ValueError):
            continue

    return found


def _json_ld_blocks(html: str) -> list[str]:
    """Contenu de chaque `<script type="application/ld+json">`.

    La fermeture n'est pas prise au premier `</script>` venu : une description
    d'annonce contient parfois du balisage, et s'arrêter là couperait le bloc
    au milieu d'une chaîne JSON — perdant tous les champs de la page pour un
    chevron. On essaie donc les fermetures successives jusqu'à ce que le JSON
    tienne debout.
    """

    blocks: list[str] = []
    for opening in _JSON_LD_OPEN.finditer(html):
        start = opening.end()
        for closing in _SCRIPT_CLOSE.finditer(html, start):
            candidate = html[start : closing.start()].strip()
            try:
                json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            blocks.append(candidate)
            break
    return blocks


def _meta_tags(html: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for name, content in _META.findall(html):
        tags.setdefault(name.lower(), content)
    for content, name in _META_REVERSED.findall(html):
        tags.setdefault(name.lower(), content)
    return tags


def _text(node: Any) -> str | None:
    """Valeur textuelle d'un nœud JSON-LD, quelle que soit sa forme.

    `schema.org` autorise une chaîne, un objet nommé (`{"@type": "Brand",
    "name": "Cartier"}`) ou une liste. On prend la première forme lisible et on
    ignore le reste : une marque n'a pas deux noms.
    """

    if node is None:
        return None
    if isinstance(node, str):
        return node
    if isinstance(node, int | float):
        return str(node)
    if isinstance(node, dict):
        for key in ("name", "value", "@value"):
            if key in node:
                return _text(node[key])
        return None
    if isinstance(node, list):
        for item in node:
            value = _text(item)
            if value is not None:
                return value
    return None


def _imported(raw: Any, value: Any, source: str, provenance: Provenance) -> Imported:
    text = clean_text(_text(raw))
    if text is None and value is None:
        return absent(source)
    return Imported(raw=text, value=value, provenance=provenance, source=source)


def _images(product: dict[str, Any], limit: int = 12) -> tuple[str, ...]:
    """URL des photos, en `https` uniquement.

    Ces adresses ne sont pas récupérées par le serveur — elles sont rendues au
    navigateur, qui les charge lui-même. Filtrer le schéma évite qu'une page
    hostile fasse afficher un `javascript:` ou un `data:` dans l'interface.
    """

    node = product.get("image")
    urls: list[str] = []

    def collect(item: Any) -> None:
        if len(urls) >= limit:
            return
        if isinstance(item, str):
            candidate = item
        elif isinstance(item, dict):
            candidate = item.get("contentUrl") or item.get("url") or ""
        elif isinstance(item, list):
            for sub in item:
                collect(sub)
            return
        else:
            return
        if isinstance(candidate, str) and candidate.startswith("https://"):
            urls.append(candidate)

    collect(node)
    return tuple(dict.fromkeys(urls))


def extract(page: FetchedPage, platform_code: str) -> ListingDraft:
    """Construit le brouillon d'annonce à partir d'une page récupérée."""

    provenance = Provenance.IMPORTED
    return _extract(page, platform_code, provenance)


def extract_assisted(page: FetchedPage, platform_code: str) -> ListingDraft:
    """Même extraction, sur un contenu fourni par l'utilisateur.

    Le traitement est identique — c'est la **provenance** qui change, et elle
    change partout : un champ importé par cette voie ne doit jamais pouvoir
    passer pour le résultat d'une récupération automatique réussie.
    """

    return _extract(page, platform_code, Provenance.ASSISTED)


def _extract(
    page: FetchedPage, platform_code: str, provenance: Provenance
) -> ListingDraft:
    html = page.text
    products = _json_ld_products(html)
    product: dict[str, Any] = products[0] if products else {}
    offer = product.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer and isinstance(offer[0], dict) else {}
    if not isinstance(offer, dict):
        offer = {}

    meta = _meta_tags(html)
    warnings: list[str] = []

    draft = ListingDraft(
        platform_code=platform_code,
        canonical_url=canonicalize_url(page.final_url),
        fetched_at=datetime.now(UTC).isoformat(),
    )

    if not products:
        warnings.append(
            "La page ne publie pas de fiche produit structurée : seuls le "
            "titre et la description ont pu être lus. Tout le reste est à "
            "saisir."
        )

    # --- Identité de l'annonce ---------------------------------------------
    draft.external_id = _imported(
        product.get("sku") or product.get("productID"),
        clean_text(_text(product.get("sku") or product.get("productID"))),
        "schema.org/Product.sku",
        provenance,
    )

    title_raw = _text(product.get("name")) or meta.get("og:title")
    draft.title = _imported(
        title_raw, clean_text(title_raw), "schema.org/Product.name", provenance
    )

    # --- Description, nettoyée et débarrassée des numéros de série ---------
    description_raw = _text(product.get("description")) or meta.get("og:description")
    description = clean_text(description_raw)
    serial_seen = False
    if description is not None:
        description, serial_seen = strip_serials(description)
    if serial_seen:
        # Règle 11 : le numéro n'entre ni dans la réponse ni dans le journal.
        # Seul le fait qu'il existait est dit, pour que l'utilisateur sache
        # que la description a été amputée.
        warnings.append(
            "L'annonce mentionne un numéro de série. Il n'a pas été importé : "
            "les numéros de série restent privés."
        )
    draft.description = (
        Imported(
            raw=description,
            value=description,
            provenance=provenance,
            source="schema.org/Product.description",
        )
        if description
        else absent("schema.org/Product.description")
    )

    # --- Montre -------------------------------------------------------------
    draft.brand = _imported(
        product.get("brand"),
        clean_text(_text(product.get("brand"))),
        "schema.org/Product.brand",
        provenance,
    )
    draft.collection = _imported(
        product.get("model"),
        clean_text(_text(product.get("model"))),
        "schema.org/Product.model",
        provenance,
    )

    # La référence constructeur, quand elle est étiquetée comme telle. Elle
    # reste **à confirmer** : c'est le vendeur qui l'a saisie, et une
    # référence fausse contamine toute la valorisation par comparables.
    reference_raw = _text(product.get("mpn")) or _text(product.get("model"))
    reference = clean_text(_text(product.get("mpn")))
    draft.reference = (
        Imported(
            raw=reference_raw,
            value=reference,
            provenance=provenance,
            source="schema.org/Product.mpn",
        )
        if reference
        else absent("schema.org/Product.mpn")
    )
    if reference:
        warnings.append(
            f"Référence « {reference} » lue dans l'annonce : elle reste à "
            "confirmer, elle n'est pas vérifiée."
        )

    year_raw = _text(product.get("productionDate")) or _text(product.get("releaseDate"))
    year = norm.year_of(year_raw)
    draft.year = (
        Imported(
            raw=clean_text(year_raw),
            value=year,
            provenance=provenance,
            source="schema.org/Product.productionDate",
        )
        if year is not None
        else absent("schema.org/Product.productionDate")
    )

    draft.case_material = _imported(
        product.get("material"),
        clean_text(_text(product.get("material"))),
        "schema.org/Product.material",
        provenance,
    )
    draft.dial = _imported(
        product.get("color"),
        clean_text(_text(product.get("color"))),
        "schema.org/Product.color",
        provenance,
    )

    # Diamètre, calibre, mouvement, bracelet et boucle : `schema.org` n'a pas
    # de champ pour eux. Ils restent absents plutôt que d'être devinés dans le
    # titre — un nombre dans un titre d'annonce est le plus souvent une
    # référence, pas une taille de boîtier.
    diameter = norm.diameter_mm_of(_text(product.get("size")))
    draft.case_diameter_mm = (
        Imported(
            raw=clean_text(_text(product.get("size"))),
            value=diameter,
            provenance=provenance,
            source="schema.org/Product.size",
        )
        if diameter is not None
        else absent("non publié par la page")
    )
    draft.movement = absent("non publié par la page")
    draft.calibre = absent("non publié par la page")
    draft.bracelet_material = absent("non publié par la page")
    draft.buckle = absent("non publié par la page")
    draft.service_history = absent("non publié par la page")
    draft.replaced_parts = absent("non publié par la page")

    # --- État déclaré -------------------------------------------------------
    condition_raw = _text(product.get("itemCondition"))
    label = norm.declared_condition_label(condition_raw)
    draft.declared_condition = (
        Imported(
            raw=label,
            value=norm.cosmetic_condition_of(condition_raw),
            provenance=provenance,
            source="schema.org/Product.itemCondition",
        )
        if label
        else absent("schema.org/Product.itemCondition")
    )
    if label and norm.cosmetic_condition_of(condition_raw) is None:
        warnings.append(
            f"L'annonce déclare l'état « {label} », ce qui ne dit rien de "
            "l'état cosmétique réel. À constater sur les photos."
        )

    # --- Boîte et papiers, séparément --------------------------------------
    haystack = " ".join(filter(None, (draft.title.raw, description)))
    box, papers, ambiguous = norm.box_and_papers(haystack or None)
    draft.box = (
        Imported(raw=None, value=box, provenance=provenance, source="mention explicite")
        if box is not None
        else absent("aucune mention explicite de la boîte")
    )
    draft.papers = (
        Imported(
            raw=None, value=papers, provenance=provenance, source="mention explicite"
        )
        if papers is not None
        else absent("aucune mention explicite des papiers")
    )
    if ambiguous:
        warnings.append(
            "L'annonce parle d'un ensemble « complet » sans dire ce qu'il "
            "contient. Boîte et papiers restent à confirmer séparément : la "
            "prime de set n'est pas la même."
        )

    # --- Prix ---------------------------------------------------------------
    price_raw = offer.get("price") or offer.get("lowPrice")
    amount = norm.amount_of(_text(price_raw))
    currency = norm.currency_of(_text(offer.get("priceCurrency")))
    draft.price_amount = (
        Imported(
            raw=clean_text(_text(price_raw)),
            value=amount,
            provenance=provenance,
            source="schema.org/Offer.price",
        )
        if amount is not None
        else absent("schema.org/Offer.price")
    )
    draft.price_currency = (
        Imported(
            raw=clean_text(_text(offer.get("priceCurrency"))),
            value=currency,
            provenance=provenance,
            source="schema.org/Offer.priceCurrency",
        )
        if currency is not None
        else absent("schema.org/Offer.priceCurrency")
    )
    kind = norm.price_kind_of(_text(offer.get("availability")))
    draft.price_kind = (
        Imported(
            raw=clean_text(_text(offer.get("availability"))),
            value=kind,
            provenance=provenance,
            source="schema.org/Offer.availability",
        )
        if kind is not None
        else absent("nature du prix non déclarée")
    )
    if amount is not None and currency is None:
        warnings.append(
            "Un montant a été lu sans devise. Il n'est pas repris : un prix "
            "sans devise ne veut rien dire."
        )
        draft.price_amount = absent("montant lu sans devise")
    if amount is not None and kind is None:
        warnings.append(
            "La nature du prix n'est pas déclarée par la page. À choisir : "
            "prix demandé, enchère en cours, prix réalisé."
        )

    # --- Vendeur ------------------------------------------------------------
    raw_seller = offer.get("seller")
    seller: dict[str, Any] = raw_seller if isinstance(raw_seller, dict) else {}
    draft.seller_name = _imported(
        seller.get("name"),
        clean_text(_text(seller.get("name"))),
        "schema.org/Offer.seller.name",
        provenance,
    )
    seller_type = norm.seller_type_of(_text(seller.get("@type")))
    draft.seller_type = (
        Imported(
            raw=clean_text(_text(seller.get("@type"))),
            value=seller_type,
            provenance=provenance,
            source="schema.org/Offer.seller.@type",
        )
        if seller_type is not None
        else absent("type de vendeur non déclaré")
    )
    raw_address = seller.get("address")
    address: dict[str, Any] = raw_address if isinstance(raw_address, dict) else {}
    country = norm.country_of(_text(address.get("addressCountry")))
    draft.seller_country = (
        Imported(
            raw=clean_text(_text(address.get("addressCountry"))),
            value=country,
            provenance=provenance,
            source="schema.org/PostalAddress.addressCountry",
        )
        if country is not None
        else absent("pays du vendeur non déclaré")
    )

    # --- Conditions de transaction -----------------------------------------
    shipping = offer.get("shippingDetails")
    draft.shipping = (
        Imported(
            raw=clean_text(json.dumps(shipping, ensure_ascii=False)),
            value=True,
            provenance=provenance,
            source="schema.org/Offer.shippingDetails",
        )
        if shipping
        else absent("conditions d'expédition non déclarées")
    )
    returns = offer.get("hasMerchantReturnPolicy")
    days = returns.get("merchantReturnDays") if isinstance(returns, dict) else None
    draft.returns = (
        Imported(
            raw=f"{days} jours" if days is not None else "politique de retour publiée",
            value=days,
            provenance=provenance,
            source="schema.org/Offer.hasMerchantReturnPolicy",
        )
        if returns
        else absent("politique de retour non déclarée")
    )
    warranty_raw = _text(product.get("warranty")) or _text(offer.get("warranty"))
    draft.warranty = _imported(
        warranty_raw, clean_text(warranty_raw), "schema.org/warranty", provenance
    )
    draft.insurance = absent("non publié par la page")

    # « Authenticité garantie » est une **déclaration du vendeur**. Elle est
    # rangée du côté vendeur et n'a aucun effet sur l'état de la montre.
    if norm.authenticity_claim(haystack or None):
        warnings.append(
            "Le vendeur déclare garantir l'authenticité. C'est une "
            "déclaration, pas une vérification : elle ne change ni l'état de "
            "la montre ni la confiance accordée à la référence."
        )

    draft.photos = _images(product)
    draft.warnings = tuple(dict.fromkeys(warnings))
    return draft
