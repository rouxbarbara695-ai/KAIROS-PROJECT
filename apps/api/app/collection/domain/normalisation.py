"""Traduire ce que la page dit. Jamais compléter ce qu'elle tait.

Chaque fonction ici prend un texte lu dans une annonce et rend `None` quand
elle ne sait pas. Ce `None` est le point important du module : il n'existe
aucun repli favorable, aucune moyenne, aucune déduction « probable ». Une
annonce muette produit un champ vide que l'utilisateur remplira, et non une
valeur plausible qu'il validera sans la regarder.

Deux pièges méritent d'être nommés, parce que ce sont ceux qui coûtent de
l'argent :

- **la boîte et les papiers se lisent séparément.** « Complet », « full set »,
  « avec accessoires » ne disent pas lequel des deux est là. La prime de set
  vaut 10 % ou 20 % selon les cas ; la deviner, c'est fausser le prix maximal
  d'achat sur la foi d'un mot publicitaire ;
- **« Authenticité garantie » est une déclaration du vendeur**, pas un
  constat. Elle est conservée telle quelle, du côté du vendeur, et ne devient
  jamais un état de la montre.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.identity.domain import vocabularies as vocab

# --- Prix ------------------------------------------------------------------

_CURRENCY_SYMBOLS = {
    "€": "EUR",
    "$": "USD",
    "£": "GBP",
    "chf": "CHF",
    "eur": "EUR",
    "usd": "USD",
    "gbp": "GBP",
    "jpy": "JPY",
}

_AMOUNT = re.compile(r"\d[\d   .,]*\d|\d")


def currency_of(raw: str | None) -> str | None:
    """Code ISO de la devise, ou `None`.

    Une devise inconnue n'est pas remplacée par l'euro : la règle 3 impose de
    conserver la devise source, et supposer l'euro sur un prix en francs
    suisses fausserait le coût de revient d'un tiers.
    """

    if raw is None:
        return None
    text = raw.strip()
    if len(text) == 3 and text.isalpha():
        return text.upper() if text.lower() in _CURRENCY_SYMBOLS else None
    for token, code in _CURRENCY_SYMBOLS.items():
        if token in text.lower():
            return code
    return None


def amount_of(raw: str | None) -> Decimal | None:
    """Montant décimal, ou `None`.

    `Decimal` et non `float` (règle 2). Les séparateurs sont ambigus d'une
    langue à l'autre — « 7,995 » vaut sept mille en anglais et sept virgule
    neuf en français — donc la règle est mécanique : le dernier séparateur
    n'est décimal que s'il est suivi d'exactement deux chiffres et qu'aucun
    autre séparateur du même type n'apparaît. Dans le doute, on ne rend rien.
    """

    if raw is None:
        return None

    match = _AMOUNT.search(raw)
    if match is None:
        return None

    text = match.group(0)
    for space in (" ", " ", " "):
        text = text.replace(space, "")

    commas, dots = text.count(","), text.count(".")
    if commas and dots:
        # Le dernier rencontré est le séparateur décimal ; l'autre groupe les
        # milliers.
        decimal_sep = "," if text.rindex(",") > text.rindex(".") else "."
        text = text.replace("," if decimal_sep == "." else ".", "")
        text = text.replace(decimal_sep, ".")
    elif commas or dots:
        sep = "," if commas else "."
        tail = text.rsplit(sep, 1)[1]
        if text.count(sep) == 1 and len(tail) in (1, 2):
            text = text.replace(sep, ".")
        else:
            text = text.replace(sep, "")

    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


# --- Nature du prix (règle 5) ----------------------------------------------

#: Correspondance entre la disponibilité `schema.org` et la nature du prix.
#: Hors de cette table, la nature reste inconnue : un prix dont on ignore s'il
#: est demandé ou réalisé n'a pas sa place dans un calcul.
_AVAILABILITY_TO_PRICE_KIND = {
    "instock": "asking",
    "limitedavailability": "asking",
    "preorder": "asking",
    "onlineonly": "asking",
    "instoreonly": "asking",
}


def price_kind_of(availability: str | None) -> str | None:
    if availability is None:
        return None
    token = availability.rsplit("/", 1)[-1].strip().lower()
    return _AVAILABILITY_TO_PRICE_KIND.get(token)


# --- État déclaré ----------------------------------------------------------

#: `schema.org/OfferItemCondition` → vocabulaire cosmétique de KAIROS.
#:
#: Seul `NewCondition` se traduit sans perte. « Used » et « Refurbished » ne
#: disent rien de l'état cosmétique — une montre d'occasion peut être
#: impeccable ou rayée — donc ils ne produisent aucune valeur. Les traduire
#: par « good » serait inventer une note.
_ITEM_CONDITION = {
    "newcondition": "excellent",
}


def cosmetic_condition_of(item_condition: str | None) -> str | None:
    if item_condition is None:
        return None
    token = item_condition.rsplit("/", 1)[-1].strip().lower()
    return _ITEM_CONDITION.get(token)


def declared_condition_label(item_condition: str | None) -> str | None:
    """Étiquette lisible de l'état **déclaré par le vendeur**, conservée telle
    quelle même quand elle ne se traduit pas."""

    if item_condition is None:
        return None
    return item_condition.rsplit("/", 1)[-1].strip() or None


# --- Boîte et papiers ------------------------------------------------------

# Mentions **explicites**, séparément pour chaque élément. Rien d'ambigu n'y
# figure : « full set », « complet », « comme neuf » en sont volontairement
# absents, parce qu'ils ne désignent ni la boîte ni les papiers en particulier.
_WITH = r"(?:avec|with|incl(?:us|uding)?\.?|comes with)"
_ARTICLE = r"(?:sa\s+|ses\s+|la\s+|les\s+|the\s+|its\s+)?"

_BOX_PRESENT = re.compile(
    rf"(?i)\b{_WITH}\s+{_ARTICLE}"
    r"(?:bo[îi]te|box|inner\s+box|outer\s+box|[ée]crin)\b"
)
_BOX_ABSENT = re.compile(
    r"(?i)\b(?:sans|no|without)\s+(?:bo[îi]te|box|[ée]crin)\b|\bbo[îi]te\s*:\s*non\b"
)
_PAPERS_PRESENT = re.compile(
    rf"(?i)\b{_WITH}\s+{_ARTICLE}"
    r"(?:papiers|papers|certificat|certificate|warranty\s+card"
    r"|carte\s+de\s+garantie)\b"
)
_PAPERS_ABSENT = re.compile(
    r"(?i)\b(?:sans|no|without)\s+(?:papiers|papers|certificat|certificate)\b"
    r"|\bpapiers\s*:\s*non\b"
)

#: Mentions qui *suggèrent* un ensemble complet sans le détailler. Elles ne
#: produisent aucune valeur : elles produisent un avertissement.
_AMBIGUOUS_SET = re.compile(
    r"(?i)\b(?:full\s*set|set\s+complet|complet|complete\s+set|tous\s+les\s+accessoires)\b"
)


def box_and_papers(text: str | None) -> tuple[bool | None, bool | None, bool]:
    """Rend `(boîte, papiers, mention_ambiguë)`.

    Chaque élément vaut `True`, `False` ou `None` — et `None` veut dire « la
    page ne le dit pas », ce qui n'est pas la même chose que « absent ». Le
    troisième booléen signale une mention du genre « full set » : elle ne
    remplit rien, elle demande une confirmation à l'utilisateur.
    """

    if text is None:
        return None, None, False

    box: bool | None = None
    if _BOX_ABSENT.search(text):
        box = False
    elif _BOX_PRESENT.search(text):
        box = True

    papers: bool | None = None
    if _PAPERS_ABSENT.search(text):
        papers = False
    elif _PAPERS_PRESENT.search(text):
        papers = True

    ambiguous = bool(_AMBIGUOUS_SET.search(text)) and (box is None or papers is None)
    return box, papers, ambiguous


# --- Vendeur ---------------------------------------------------------------

_COUNTRY = re.compile(r"^[A-Za-z]{2}$")


def country_of(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    return text.upper() if _COUNTRY.match(text) else None


def seller_type_of(raw: str | None) -> str | None:
    """« Organization » désigne un marchand, « Person » un particulier.

    Toute autre valeur ne rend rien : `vocab.normalize` retomberait sur
    « unknown », ce qui est correct pour une saisie mais faux ici — on veut
    distinguer « la page dit qu'on ne sait pas » de « la page ne dit rien ».
    """

    if raw is None:
        return None
    token = raw.strip().lower()
    if token in ("organization", "organisation", "professional", "dealer", "store"):
        return "professional"
    if token in ("person", "private", "individual"):
        return "private"
    return None


# --- Dimensions et millésime ----------------------------------------------

_DIAMETER = re.compile(r"(?i)(\d{2}(?:[.,]\d)?)\s*mm")
# Ancré : la chaîne entière doit être un millésime, ou une date qui commence
# par lui. Chercher une année *dans* un texte lirait « 1861 » dans
# « Speedmaster 1861 », qui est une référence de calibre.
_YEAR = re.compile(r"^\s*(1[89]\d{2}|20\d{2})(?:[-/].*)?\s*$")


def diameter_mm_of(raw: str | None) -> Decimal | None:
    """Diamètre en millimètres, uniquement s'il est écrit avec son unité.

    Un nombre isolé dans un titre n'est pas un diamètre : « Submariner 116610 »
    en contient trois qui n'en sont pas.
    """

    if raw is None:
        return None
    match = _DIAMETER.search(raw)
    if match is None:
        return None
    try:
        value = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:  # pragma: no cover - le motif garantit la forme
        return None
    # Une montre-bracelet mesure entre 20 et 60 mm. Hors de cette plage, c'est
    # autre chose qui a été lu — une longueur de bracelet, une épaisseur.
    return value if Decimal(20) <= value <= Decimal(60) else None


def year_of(raw: str | None) -> int | None:
    """Millésime d'un champ **étiqueté** comme tel.

    N'accepte que la valeur entière — « 2019 », « 2019-04-01 » — jamais une
    année trouvée dans une phrase. Une référence horlogère contient souvent
    quatre chiffres qui ressemblent à une année : « Speedmaster 1861 » désigne
    un calibre, pas un millésime, et le lire comme tel mettrait dans le dossier
    une date que personne n'a écrite.
    """

    if raw is None:
        return None
    match = _YEAR.match(raw)
    if match is None:
        return None
    year = int(match.group(1))
    return year if 1850 <= year <= 2100 else None


# --- Authenticité ----------------------------------------------------------

_AUTHENTICITY_CLAIM = re.compile(
    r"(?i)\b(?:authenticit[ée]\s+garantie|guaranteed\s+authentic|authenticity\s+"
    r"guarantee[d]?|certifi[ée]\s+authentique)\b"
)


def authenticity_claim(text: str | None) -> bool:
    """La page **déclare** l'authenticité.

    Rendu comme une déclaration du vendeur, à ranger du côté vendeur. Ce n'est
    pas une vérification, et cela ne touche ni l'originalité de la montre ni la
    confiance accordée à la référence.
    """

    return bool(text and _AUTHENTICITY_CLAIM.search(text))


def to_mechanical(raw: str | None) -> str:
    return vocab.normalize(raw, vocab.MECHANICAL_CONDITIONS, vocab.MECHANICAL_FALLBACK)
