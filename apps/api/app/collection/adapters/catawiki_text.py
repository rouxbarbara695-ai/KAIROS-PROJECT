"""Lire un lot Catawiki dans le texte que l'utilisateur a copié.

**Pourquoi ce module existe.** Catawiki refuse toute requête serveur : le bord
Akamai répond `403` sur tous ses domaines, y compris `robots.txt` et les pages
de lot, quel que soit l'agent annoncé. Il n'existe pas d'API publique côté
acheteur. Contourner ce contrôle est exclu. Le seul chemin honnête est donc
que l'utilisateur ouvre le lot dans son navigateur — où il est un visiteur
ordinaire — et colle ce qu'il voit.

**Ce qu'il colle est du texte visible**, pas du code source. Pas de `Ctrl+U`,
pas d'outils de développement : `Ctrl+A`, `Ctrl+C`, coller. Cela change tout
pour l'extraction — il n'y a plus de `schema.org` à lire, seulement des
étiquettes et des valeurs, dans l'ordre où la page les affiche, dans la langue
de l'utilisateur.

**La méthode est donc l'étiquette, jamais la position.** Un champ n'est rempli
que si le texte porte une étiquette qui le nomme. Aucune valeur n'est déduite
d'un rang dans une liste : la mise en page de Catawiki changera, les étiquettes
bien moins vite, et une extraction positionnelle se tromperait en silence le
jour où une ligne s'ajoute.

**Ce qui n'est jamais rempli** : un montant sans devise ; une heure de clôture
sans fuseau ; des frais de livraison dont la destination n'est pas nommée ;
une réserve dont la page ne dit rien. Chacun de ces cas produit un
avertissement, pas une valeur.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal

from app.collection.domain import normalisation as norm
from app.collection.domain.fields import Imported, ListingDraft, Provenance, absent
from app.collection.domain.sanitize import clean_text, strip_serials
from app.opportunities.domain.canonical_url import canonicalize_url

PLATFORM_CODE = "catawiki"

# Le numéro de lot vit dans l'URL (`/l/12345678-…`) et souvent aussi dans le
# texte. L'URL fait foi : elle est fournie séparément et ne dépend pas de la
# langue d'affichage.
_LOT_IN_URL = re.compile(r"/l/(\d{5,})")

#: « 1990-1999 », « 2010–2020 » : une fourchette, jamais un millésime.
_PERIOD = re.compile(r"^\s*\d{4}\s*[-–—]\s*\d{4}\s*$")
_LOT_IN_TEXT = re.compile(
    r"(?i)\b(?:num[ée]ro\s+de\s+lot|lot\s*(?:number|nummer|n[°o]?)|kavelnummer)\s*[:#]?\s*(\d{5,})"
)

# --- Étiquettes -------------------------------------------------------------
#
# Catawiki sert le même lot en français, anglais et néerlandais selon le
# visiteur. Les trois sont acceptées : l'utilisateur ne doit pas avoir à
# changer la langue de son compte pour que l'import fonctionne.
#
# Ce tableau est une **configuration**, pas une règle métier : le corriger
# quand Catawiki renomme une étiquette est une modification de données, pas de
# logique.
_SPEC_LABELS: dict[str, tuple[str, ...]] = {
    "brand": ("marque", "brand", "merk"),
    "collection": ("modèle", "modele", "model"),
    "reference": (
        "numéro de référence",
        "numero de reference",
        "référence",
        "reference number",
        "reference",
        "referentienummer",
    ),
    "year": ("année", "annee", "year", "jaar", "période", "periode", "period"),
    "movement": ("mouvement", "movement", "uurwerk", "type de mouvement"),
    "calibre": ("calibre", "caliber", "kaliber"),
    "case_material": (
        "matériau du boîtier",
        "materiau du boitier",
        "matériau boîtier",
        "case material",
        "kastmateriaal",
        "matière du boîtier",
    ),
    "case_diameter_mm": (
        "diamètre du boîtier",
        "diametre du boitier",
        "diamètre",
        "case diameter",
        "kastdiameter",
        "largeur du boîtier",
    ),
    "dial": ("cadran", "couleur du cadran", "dial", "dial colour", "wijzerplaat"),
    "bracelet_material": (
        "matériau du bracelet",
        "materiau du bracelet",
        "bracelet",
        "strap material",
        "band material",
        "bandmateriaal",
    ),
    "buckle": ("boucle", "fermoir", "clasp", "buckle", "sluiting"),
    "declared_condition": ("état", "etat", "condition", "staat", "état de la montre"),
    "service_history": (
        "révision",
        "revision",
        "dernière révision",
        "service history",
        "serviced",
        "onderhoud",
    ),
    "seller_country": ("pays", "country", "land", "pays du vendeur"),
    # Constatées sur des lots réels : Catawiki publie garantie et assurance
    # comme des lignes à part entière.
    "warranty": (
        "original warranty included",
        "garantie d'origine incluse",
        "garantie incluse",
        "originele garantie inbegrepen",
    ),
    "insurance": (
        "shipped insured",
        "envoi assuré",
        "expédition assurée",
        "verzekerd verzonden",
    ),
}

# Boîte et papiers : lus **séparément**, et seulement sur une étiquette qui les
# nomme. Catawiki a des lignes dédiées, ce qui évite d'avoir à interpréter
# « complet » dans une description publicitaire.
_BOX_LABELS = (
    "boîte d'origine incluse",
    "boite d'origine incluse",
    "boîte d'origine",
    "boîte incluse",
    "original box included",
    "box included",
    "originele doos inbegrepen",
)
_PAPERS_LABELS = (
    "papiers d'origine inclus",
    "papiers d'origine",
    "documents d'origine inclus",
    "papiers inclus",
    "certificat inclus",
    "original papers included",
    "papers included",
    "certificate included",
    "originele papieren inbegrepen",
)

_YES = ("oui", "yes", "ja", "inclus", "included", "inbegrepen")
_NO = ("non", "no", "nee", "non inclus", "not included", "niet inbegrepen")

# --- Enchère ----------------------------------------------------------------

_BID_LABELS = (
    "enchère actuelle",
    "enchere actuelle",
    "offre actuelle",
    "enchère en cours",
    "mise actuelle",
    "current bid",
    "latest bid",
    "huidig bod",
)
# Le nombre et le mot doivent être sur la **même ligne**, séparés par de
# simples espaces. Avec `\s*`, « … 1990-1999 » suivi d'un saut de ligne et de
# « Enchère actuelle » se lisait « 1999 enchères » — un millésime pris pour un
# compteur.
_BID_COUNT = re.compile(r"(?i)(\d+)[  \t]*(?:enchères?|offres?|bids?|biedingen?)\b")
_ESTIMATE_LABELS = (
    "estimation catawiki",
    "estimation de l'expert",
    "estimation",
    "catawiki estimate",
    "estimate",
    "geschatte waarde",
    "schatting",
)
_CLOSING_LABELS = (
    "se termine le",
    "clôture le",
    "cloture le",
    "fin de l'enchère",
    "date de clôture",
    "closes on",
    "closing date",
    "ends on",
    "sluit op",
)

_NO_RESERVE = (
    "pas de prix de réserve",
    "pas de prix de reserve",
    "sans prix de réserve",
    "aucun prix de réserve",
    "no reserve price",
    "no reserve",
    "geen reserveprijs",
)
_RESERVE_NOT_MET = (
    "prix de réserve non atteint",
    "prix de reserve non atteint",
    "réserve non atteinte",
    "reserve price not met",
    "reserve not met",
    "reserveprijs niet gehaald",
)
_RESERVE_MET = (
    "prix de réserve atteint",
    "prix de reserve atteint",
    "réserve atteinte",
    "reserve price met",
    "reserve met",
    "reserveprijs gehaald",
)

_SELLER_LABELS = ("vendeur", "seller", "verkoper", "vendu par", "sold by")

# Table de correspondance, pas une règle métier : Catawiki écrit le pays en
# toutes lettres, le formulaire attend un code ISO à deux lettres. Un pays
# absent de la table garde son libellé plutôt que d'être deviné.
_COUNTRY_NAMES: dict[str, str] = {
    "france": "FR",
    "belgique": "BE",
    "belgië": "BE",
    "belgium": "BE",
    "pays-bas": "NL",
    "nederland": "NL",
    "netherlands": "NL",
    "allemagne": "DE",
    "deutschland": "DE",
    "germany": "DE",
    "italie": "IT",
    "italia": "IT",
    "italy": "IT",
    "espagne": "ES",
    "españa": "ES",
    "spain": "ES",
    "suisse": "CH",
    "schweiz": "CH",
    "switzerland": "CH",
    "royaume-uni": "GB",
    "united kingdom": "GB",
    "portugal": "PT",
    "autriche": "AT",
    "austria": "AT",
}


def _country(value: str) -> str | None:
    return norm.country_of(value) or _COUNTRY_NAMES.get(value.strip().lower())


_SELLER_SINCE = re.compile(
    r"(?i)\b(?:membre depuis|vendeur depuis|member since|lid sinds)\s*:?\s*(\d{4})"
)

# --- France -----------------------------------------------------------------
#
# La destination doit être **nommée**. Un montant de livraison isolé n'est pas
# repris : Catawiki affiche souvent le tarif du pays du visiteur, et prendre un
# tarif néerlandais pour un tarif français fausse le coût de revient sans que
# rien ne le signale.
_FRANCE = ("france", "frankrijk", "vers la france", "to france", "naar frankrijk")
_SHIPPING_LABELS = (
    "frais d'expédition",
    "frais d'envoi",
    "frais de livraison",
    "livraison",
    "expédition",
    "shipping costs",
    "shipping",
    "verzendkosten",
)

# --- Motifs de valeur -------------------------------------------------------

_CURRENCY_SIGN = r"(?:€|EUR|\$|USD|£|GBP|CHF)"
_NUMBER = r"\d[\d  .,  ]*\d|\d"
_MONEY = re.compile(
    rf"(?:(?P<before>{_CURRENCY_SIGN})\s*(?P<amount1>{_NUMBER})"
    rf"|(?P<amount2>{_NUMBER})\s*(?P<after>{_CURRENCY_SIGN}))"
)
_RANGE_SEPARATOR = re.compile(r"\s*(?:-|–|—|à|to|tot|et)\s*")

_MONTHS = {
    m: i
    for i, names in enumerate(
        (
            ("janvier", "january", "januari", "jan"),
            ("février", "fevrier", "february", "februari", "feb", "fév"),
            ("mars", "march", "maart", "mar"),
            ("avril", "april", "apr", "avr"),
            ("mai", "may", "mei"),
            ("juin", "june", "juni", "jun"),
            ("juillet", "july", "juli", "jul"),
            ("août", "aout", "august", "augustus", "aug"),
            ("septembre", "september", "sept", "sep"),
            ("octobre", "october", "oktober", "oct", "okt"),
            ("novembre", "november", "nov"),
            ("décembre", "decembre", "december", "dec", "déc"),
        ),
        start=1,
    )
    for m in names
}

_DATE_TEXT = re.compile(
    r"(?i)\b(\d{1,2})\s+([a-zéûôàè]+)\.?\s+(\d{4})\b"
    r"(?:[^0-9]{0,12}(\d{1,2})\s*[:hH]\s*(\d{2}))?"
)
_DATE_NUMERIC = re.compile(
    r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b(?:[^0-9]{0,12}(\d{1,2})\s*[:hH]\s*(\d{2}))?"
)
_TIMEZONE = re.compile(
    r"(?i)\b(CES?T|UTC|GMT|BST|WEST|WET)\b|\b(?:UTC|GMT)\s*([+-]\d{1,2})(?::?(\d{2}))?"
)
# Catawiki n'affiche **jamais** de date de clôture absolue : il montre un
# compte à rebours (« Closes in 23h 28m 23s »), un décompte éclaté sur
# plusieurs lignes (« 00 / days / 23 / hours »), ou un repère relatif
# (« Tomorrow 20:26 », « Thursday 21:58 »). Aucun n'est convertible sans
# supposer l'instant du collage — et une fin d'enchère fausse d'une heure se
# rate. On les reconnaît pour **le dire**, pas pour les convertir.
_COUNTDOWN_PATTERNS = (
    re.compile(r"(?i)\bcloses?\s+in\b"),
    re.compile(r"(?i)\b(?:se\s+termine|fin)\s+dans\b"),
    re.compile(r"(?i)\b\d+\s*d\s*\d+\s*[mh]\b"),
    re.compile(r"(?i)\b\d+\s*h\s*\d+\s*m\b"),
    re.compile(r"(?i)^(?:days?|hours?|minutes?|seconds?|jours?|heures?)$"),
)
_RELATIVE_DAY = re.compile(
    r"(?i)^((?:tomorrow|today|aujourd'hui|demain"
    r"|mon|tues|wednes|thurs|fri|satur|sun)[a-zéû]*"
    r"|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2}:\d{2})$"
)


def _countdown_seen(lines: list[str]) -> str | None:
    """Repère relatif affiché, s'il y en a un. Rendu tel quel, jamais converti."""

    for line in lines:
        if _RELATIVE_DAY.match(line):
            return line
        for pattern in _COUNTDOWN_PATTERNS:
            if pattern.search(line):
                return line
    return None


_SECTION_END = (
    "seller's story",
    "show more",
    "details",
    "shipping",
    "l'histoire du vendeur",
    "voir plus",
    "caractéristiques",
)
_DESCRIPTION_START = (
    "description from the seller",
    "description du vendeur",
    "beschrijving van de verkoper",
    "description",
)


def _title_line(lines: list[str], brand: object) -> str | None:
    """Ligne de titre du lot, reconnue par la marque et le gabarit à tirets.

    La première ligne du collage est du menu (« Search for brand, model,
    artist… ») : la prendre pour un titre remplirait le dossier avec du
    chrome. Sans marque connue, on rend `None` — une absence vaut mieux qu'un
    morceau d'interface.
    """

    if not isinstance(brand, str) or not brand:
        return None
    prefix = brand.lower()
    for line in lines:
        lowered = line.lower()
        if lowered.startswith(prefix) and " - " in line and "#" not in line:
            return line
    return None


def _seller_description(lines: list[str]) -> str | None:
    """Section écrite par le vendeur, sans le reste de la page.

    S'arrête à « Seller's Story » — la présentation commerciale de la
    boutique, qui ne dit rien de la montre — et aux repères de section
    suivants. Sans cette borne, la description emporterait le menu,
    l'historique des enchères et les autres lots du vendeur.
    """

    start: int | None = None
    for index, line in enumerate(lines):
        if line.strip().lower().rstrip(":") in _DESCRIPTION_START:
            start = index + 1
            break
    if start is None:
        return None

    body: list[str] = []
    for line in lines[start:]:
        if line.strip().lower() in _SECTION_END:
            break
        body.append(line)
    text = "\n".join(body).strip()
    return text or None


_BUYER_FEE = re.compile(
    r"(?i)(?:buyer\s+protection\s+fee|frais\s+de\s+protection|commission\s+acheteur)"
    r"\s*:?\s*(\d{1,2}(?:[.,]\d+)?)\s*%"
    r"(?:\s*\+\s*(€|EUR|\$|£)?\s*(\d+(?:[.,]\d{1,2})?))?"
)

#: Le calibre est rarement une ligne à lui seul : le vendeur l'écrit dans la
#: phrase de mouvement (« Caliber Omega 1456 », « Calibre JLC 846 »). Le mot
#: « calibre » suivi d'un identifiant est une déclaration explicite — la lire
#: n'est pas deviner. Un éventuel nom de marque intercalé est ignoré.
_CALIBRE_IN_TEXT = re.compile(
    r"(?i)\b(?:calibre|caliber|kaliber|cal\.)\s*"
    r"(?:[A-Za-zÀ-ÿ&.-]+\s+){0,2}"
    r"([0-9][0-9A-Za-z./-]{1,15})\b"
)

#: Révision **déclarée** par le vendeur. Ni date ni vérification ne s'en
#: déduisent : « Serviced » dit qu'on l'affirme, pas quand ni par qui.
_SERVICE_DECLARED = re.compile(
    r"(?i)\b(serviced|r[ée]vis[ée]e?|overhaul(?:ed)?|onderhouden|"
    r"service\s+complet|full\s+service)\b"
)

_SHIPS_FROM = re.compile(r"(?i)^ships?\s+from\s+([A-Z]{2})$")
_PROFESSIONAL = re.compile(
    r"(?i)sold\s+by\s+a\s+professional\s+seller"
    r"|vendu\s+par\s+un\s+(?:vendeur\s+)?professionnel"
)

#: Contradiction fréquente : la fiche technique arrondit le diamètre
#: (« 21 mm ») là où la description du vendeur donne la mesure réelle
#: (« 20,7 mm »). On signale, on n'arbitre pas.
_DIAMETER_IN_TEXT = re.compile(
    r"(?i)(?:case\s+diameter|diam[èe]tre\s+(?:du\s+)?bo[îi]tier)[^\n\d]{0,40}"
    r"(\d{2}(?:[.,]\d)?)\s*mm"
)


def _money(text: str) -> tuple[Decimal | None, str | None]:
    """Montant et devise d'un fragment, ou `(None, None)`.

    Les deux ensemble ou rien : un montant sans devise n'est pas une donnée
    exploitable, et lui prêter l'euro fausserait le coût de revient d'un tiers
    sur un lot facturé en francs suisses (règle 3).
    """

    match = _MONEY.search(text)
    if match is None:
        return None, None
    raw_amount = match.group("amount1") or match.group("amount2")
    sign = match.group("before") or match.group("after")
    amount = norm.amount_of(raw_amount)
    currency = norm.currency_of(sign)
    if amount is None or currency is None:
        return None, None
    return amount, currency


def _normalise_lines(text: str) -> list[str]:
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = clean_text(raw)
        if cleaned:
            lines.append(cleaned)
    return lines


def _label_of(line: str) -> str:
    """Partie gauche d'une ligne « Étiquette : valeur », en minuscules."""

    head = line.split(":", 1)[0] if ":" in line else line
    return head.strip().lower().rstrip("*").strip()


def _value_after(line: str) -> str | None:
    if ":" not in line:
        return None
    value = line.split(":", 1)[1].strip()
    return value or None


def _matches(label: str, candidates: tuple[str, ...]) -> bool:
    return any(label == candidate for candidate in candidates)


#: Début de la fiche technique de Catawiki. Ce qui suit est **structuré** :
#: des champs que la plateforme impose au vendeur, pas de la prose.
_DETAILS_MARKERS = ("details", "caractéristiques", "kenmerken", "détails")


def _details_section(lines: list[str]) -> list[str]:
    """Lignes de la fiche technique, si la page en publie une."""

    for index, line in enumerate(lines):
        if line.strip().lower() in _DETAILS_MARKERS:
            return lines[index + 1 :]
    return []


def find_value(
    lines: list[str], candidates: tuple[str, ...]
) -> tuple[str | None, str | None]:
    """Valeur de la fiche technique, et celle de la description si elle diffère.

    **La fiche technique l'emporte.** Le vendeur écrit aussi « Movement: … »
    dans sa prose, souvent en plus bavard (« High-precision Swiss quartz,
    Caliber Omega 1456 (as indicated on the pictogram card) ») là où la fiche
    dit « Quartz ». Prendre la prose parce qu'elle apparaît plus haut dans la
    page remplirait le formulaire de phrases.

    Quand les deux existent et divergent, la seconde est rendue comme
    **contradiction** : elle est signalée, jamais arbitrée. C'est le cas du
    diamètre, que la fiche arrondit (« 22 mm ») et que la description donne au
    dixième (« 22.5 mm »).
    """

    structured = _details_section(lines)
    from_details = _find_labelled(structured, candidates) if structured else None
    from_anywhere = _find_labelled(lines, candidates)

    if from_details is None:
        return from_anywhere, None
    if from_anywhere is None or _same(from_details, from_anywhere):
        return from_details, None
    # La description développe la fiche sans la contredire : on garde la
    # version courte, qui est celle du champ structuré, et on ne signale rien.
    if _elaborates(from_details, from_anywhere) or _elaborates(
        from_anywhere, from_details
    ):
        return from_details, None
    return from_details, from_anywhere


_WORD = re.compile(r"[\w'-]+", re.UNICODE)
#: Mots vides du vocabulaire horloger : leur absence d'un côté ne dit rien.
_IGNORED_WORDS = frozenset(
    {
        "de",
        "du",
        "la",
        "le",
        "les",
        "des",
        "and",
        "with",
        "the",
        "a",
        "an",
        "et",
        "en",
        "of",
        "type",
        "colour",
        "color",
        "material",
    }
)


def _fold(text: str) -> str:
    """Minuscule, sans accent ni ponctuation de fin.

    « Must de Cartier Vendôme. » et « Must de Cartier Vendome » sont le même
    modèle : les traiter comme divergents ferait crier au loup sur un accent.
    """

    stripped = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in stripped if not unicodedata.combining(c))
    return without_accents.strip().lower().rstrip(".").strip()


def _words(text: str) -> set[str]:
    return {word for word in _WORD.findall(_fold(text)) if word not in _IGNORED_WORDS}


def _elaborates(summary: str, detail: str) -> bool:
    """La seconde formulation dit-elle la même chose, en plus détaillé ?

    C'est le cas courant sur Catawiki : la fiche technique impose un mot
    (« Quartz », « Steel ») et le vendeur développe dans sa prose
    (« High-precision Swiss quartz, Caliber Omega 1456 », « Stainless steel.
    Fixed bezel… »). Les deux sont compatibles, et les présenter comme une
    contradiction apprendrait à l'utilisateur à ignorer les alertes — après
    quoi il ignorerait aussi les vraies.

    Le critère est mécanique : tous les mots significatifs de la version
    courte se retrouvent dans la longue.
    """

    short, long = _words(summary), _words(detail)
    return bool(short) and short <= long


def _same(left: str, right: str) -> bool:
    return _fold(left) == _fold(right)


def _find_labelled(lines: list[str], candidates: tuple[str, ...]) -> str | None:
    """Valeur associée à l'une des étiquettes, quelle que soit la disposition.

    Catawiki présente ses caractéristiques tantôt en « Étiquette : valeur » sur
    une ligne, tantôt sur deux lignes successives quand la page est copiée
    depuis un tableau. Les deux formes sont acceptées ; aucune autre ne l'est,
    faute de quoi on lirait la ligne suivante d'un paragraphe comme une valeur.
    """

    for index, line in enumerate(lines):
        label = _label_of(line)
        if not _matches(label, candidates):
            continue
        inline = _value_after(line)
        if inline:
            return inline
        if index + 1 < len(lines):
            following = lines[index + 1]
            # La ligne suivante ne doit pas être elle-même une étiquette
            # connue : deux étiquettes qui se suivent signifient une valeur
            # manquante, pas une valeur qui vaut « l'étiquette d'après ».
            if not _is_known_label(_label_of(following)):
                return following
    return None


_ALL_LABELS: tuple[str, ...] = tuple(
    label
    for group in (
        *_SPEC_LABELS.values(),
        _BOX_LABELS,
        _PAPERS_LABELS,
        _BID_LABELS,
        _ESTIMATE_LABELS,
        _CLOSING_LABELS,
        _SELLER_LABELS,
        _SHIPPING_LABELS,
    )
    for label in group
)


def _is_known_label(label: str) -> bool:
    return label in _ALL_LABELS


def _yes_no(value: str | None) -> bool | None:
    if value is None:
        return None
    token = value.strip().lower().rstrip(".")
    if any(token.startswith(word) for word in _YES):
        return True
    if any(token.startswith(word) for word in _NO):
        return False
    return None


def _imported(
    raw: str | None, value: object, source: str, provenance: Provenance
) -> Imported:
    if raw is None and value is None:
        return absent(source)
    return Imported(raw=raw, value=value, provenance=provenance, source=source)


def _closing(lines: list[str], text: str) -> tuple[Imported, Imported, list[str]]:
    """Date de clôture et fuseau, ou rien — avec la raison.

    Un compte à rebours (« 2 j 03 h ») n'est **pas** converti en date. Le faire
    supposerait que le collage a eu lieu à l'instant, alors qu'il peut dater
    d'une heure : on obtiendrait une heure de fin fausse d'une heure, ce qui
    est exactement la façon de rater une enchère.
    """

    warnings: list[str] = []
    labelled = _find_labelled(lines, _CLOSING_LABELS)
    haystack = labelled or text

    parsed: datetime | None = None
    raw_date: str | None = None

    match = _DATE_TEXT.search(haystack)
    if match is not None:
        month = _MONTHS.get(match.group(2).lower().rstrip("."))
        if month is not None:
            raw_date = match.group(0)
            parsed = datetime(
                int(match.group(3)),
                month,
                int(match.group(1)),
                int(match.group(4) or 0),
                int(match.group(5) or 0),
            )

    if parsed is None:
        numeric = _DATE_NUMERIC.search(haystack)
        if numeric is not None:
            raw_date = numeric.group(0)
            parsed = datetime(
                int(numeric.group(3)),
                int(numeric.group(2)),
                int(numeric.group(1)),
                int(numeric.group(4) or 0),
                int(numeric.group(5) or 0),
            )

    zone_match = _TIMEZONE.search(haystack) or _TIMEZONE.search(text)
    zone = zone_match.group(0).strip() if zone_match else None

    if parsed is None:
        countdown = _countdown_seen(lines)
        if countdown is not None:
            warnings.append(
                f"Clôture affichée en relatif (« {countdown} »), pas en date. "
                "Elle n'est pas convertie : le collage peut dater d'une heure, "
                "et une fin d'enchère fausse d'une heure se rate. La date "
                "exacte est sur Catawiki, à saisir à la main."
            )
            return (
                Imported(
                    raw=countdown,
                    value=None,
                    provenance=Provenance.ASSISTED,
                    source="repère relatif affiché, non converti",
                ),
                absent("aucun fuseau affiché"),
                warnings,
            )
        return (
            absent("date de clôture non trouvée"),
            absent("fuseau non trouvé"),
            warnings,
        )

    if zone is None:
        warnings.append(
            f"Clôture lue « {raw_date} », mais la page n'indique aucun fuseau "
            "horaire. L'heure n'est pas reprise : se tromper d'une heure sur "
            "une fin d'enchère, c'est la rater. Vérifier sur Catawiki."
        )
        return (
            Imported(
                raw=raw_date,
                value=None,
                provenance=Provenance.ASSISTED,
                source="clôture sans fuseau",
            ),
            absent("fuseau non indiqué par la page"),
            warnings,
        )

    return (
        Imported(
            raw=raw_date,
            value=parsed.isoformat(),
            provenance=Provenance.ASSISTED,
            source="date de clôture affichée",
        ),
        Imported(
            raw=zone,
            value=zone,
            provenance=Provenance.ASSISTED,
            source="fuseau affiché",
        ),
        warnings,
    )


def _shipping_to_france(
    lines: list[str],
) -> tuple[Imported, Imported, Imported, str | None]:
    """Frais de livraison **vers la France**, et seulement vers la France.

    La destination doit être nommée sur la même ligne, ou sur la ligne portant
    l'étiquette. Un tarif isolé n'est pas repris : Catawiki affiche le tarif du
    pays du visiteur, et rien ne garantit que ce soit la France.
    """

    for index, line in enumerate(lines):
        lowered = line.lower()
        mentions_france = any(token in lowered for token in _FRANCE)
        is_shipping_label = _matches(_label_of(line), _SHIPPING_LABELS) or any(
            token in lowered for token in _SHIPPING_LABELS
        )
        if not (mentions_france and is_shipping_label):
            continue

        amount, currency = _money(line)
        if amount is None and index + 1 < len(lines):
            amount, currency = _money(lines[index + 1])
        if amount is None or currency is None:
            continue

        return (
            Imported(
                raw=line,
                value=amount,
                provenance=Provenance.ASSISTED,
                source="frais de livraison vers la France",
            ),
            Imported(
                raw=currency,
                value=currency,
                provenance=Provenance.ASSISTED,
                source="frais de livraison vers la France",
            ),
            Imported(
                raw="France",
                value="FR",
                provenance=Provenance.ASSISTED,
                source="destination nommée dans l'annonce",
            ),
            None,
        )

    # Des frais existent mais sans destination nommée : on le dit, on ne
    # suppose pas.
    for line in lines:
        if any(token in line.lower() for token in _SHIPPING_LABELS):
            amount, _ = _money(line)
            if amount is not None:
                return (
                    absent("frais trouvés, destination non nommée"),
                    absent("frais trouvés, destination non nommée"),
                    absent("destination non nommée"),
                    "Des frais de livraison apparaissent, mais la page ne dit "
                    "pas pour quelle destination. Ils ne sont pas repris : un "
                    "tarif d'un autre pays fausserait le coût de revient.",
                )

    return (
        absent("frais de livraison non affichés"),
        absent("frais de livraison non affichés"),
        absent("destination non affichée"),
        None,
    )


def _reserve(text: str) -> Imported:
    lowered = text.lower()
    for tokens, status in (
        (_NO_RESERVE, "no_reserve"),
        (_RESERVE_NOT_MET, "not_met"),
        (_RESERVE_MET, "met"),
    ):
        for token in tokens:
            if token in lowered:
                return Imported(
                    raw=token,
                    value=status,
                    provenance=Provenance.ASSISTED,
                    source="mention explicite du prix de réserve",
                )
    # L'absence de mention ne vaut pas « pas de réserve ».
    return absent("aucune mention du prix de réserve")


def _estimate(lines: list[str]) -> tuple[Imported, Imported, Imported]:
    """Estimation **de Catawiki**, conservée à part.

    Elle n'entre dans aucun calcul de KAIROS. Le schéma distingue d'ailleurs
    `external_estimate` de `kairos_estimate` : les confondre reviendrait à
    valider une valorisation par l'avis du vendeur.
    """

    value = _find_labelled(lines, _ESTIMATE_LABELS)
    if value is None:
        return (
            absent("estimation non affichée"),
            absent("estimation non affichée"),
            absent("estimation non affichée"),
        )

    parts = _RANGE_SEPARATOR.split(value)
    low, currency = _money(parts[0]) if parts else (None, None)
    high, high_currency = _money(parts[1]) if len(parts) > 1 else (None, None)

    # Une borne sans devise n'est pas reprise ; une fourchette dont les deux
    # bornes ne concordent pas non plus.
    if low is None:
        return (
            absent("estimation illisible"),
            absent("estimation illisible"),
            absent("estimation illisible"),
        )
    if high is not None and high_currency != currency:
        high = None

    return (
        Imported(
            raw=value,
            value=low,
            provenance=Provenance.ASSISTED,
            source="estimation Catawiki",
        ),
        (
            Imported(
                raw=value,
                value=high,
                provenance=Provenance.ASSISTED,
                source="estimation Catawiki",
            )
            if high is not None
            else absent("estimation sans borne haute")
        ),
        Imported(
            raw=currency,
            value=currency,
            provenance=Provenance.ASSISTED,
            source="estimation Catawiki",
        ),
    )


def extract(text: str, url: str) -> ListingDraft:
    """Construit le brouillon d'un lot Catawiki depuis le texte collé."""

    provenance = Provenance.ASSISTED
    lines = _normalise_lines(text)
    joined = "\n".join(lines)
    warnings: list[str] = []

    draft = ListingDraft(
        platform_code=PLATFORM_CODE,
        canonical_url=canonicalize_url(url) if url else "",
        fetched_at=datetime.now(UTC).isoformat(),
    )
    for name in (
        "replaced_parts",
        "seller_type",
        "insurance",
        "warranty",
        "returns",
        "shipping",
        "buyer_fee_rate",
        "buyer_fee_fixed",
        "buyer_fee_currency",
        "production_period",
    ):
        setattr(draft, name, absent("non affiché par l'annonce"))

    # --- Numéro de lot ------------------------------------------------------
    lot_from_url = _LOT_IN_URL.search(url or "")
    lot_from_text = _LOT_IN_TEXT.search(joined)
    lot = (
        lot_from_url.group(1)
        if lot_from_url
        else (lot_from_text.group(1) if lot_from_text else None)
    )
    draft.lot_number = _imported(
        lot,
        lot,
        "numéro de lot dans l'URL" if lot_from_url else "numéro de lot affiché",
        provenance,
    )
    draft.external_id = draft.lot_number
    if (
        lot_from_url
        and lot_from_text
        and lot_from_url.group(1) != lot_from_text.group(1)
    ):
        warnings.append(
            "Le numéro de lot du lien et celui du texte diffèrent : le lien "
            "fait foi. Vérifier que le texte collé est bien celui de ce lot."
        )

    # --- Caractéristiques ---------------------------------------------------
    for name, labels in _SPEC_LABELS.items():
        value, disagreement = find_value(lines, labels)
        if value is None:
            setattr(draft, name, absent("non affiché par l'annonce"))
            continue

        normalised: object = value
        if name == "reference":
            # Les vendeurs ajoutent un qualificatif dans le champ référence —
            # « 266.1.44 - Serviced ». Ce n'est pas la référence, et une
            # référence ainsi polluée ne retrouverait aucun comparable. Le
            # qualificatif est retiré de la valeur ; le brut reste consultable,
            # et la référence reste « à confirmer » de toute façon.
            normalised = value.split(" - ", 1)[0].strip() or None
        elif name == "year":
            # « 1990-1999 » est une **période**, pas une année. En retenir la
            # borne basse inventerait une précision que la page ne donne pas ;
            # la valeur brute reste consultable et l'utilisateur tranche.
            if _PERIOD.match(value):
                # Information réelle et utile : on la conserve **comme
                # période**, visible et modifiable, plutôt que de la jeter ou
                # d'en tirer une année exacte que la page ne donne pas.
                draft.production_period = Imported(
                    raw=value,
                    value=value,
                    provenance=provenance,
                    source="période de production affichée",
                )
                normalised = None
            else:
                normalised = norm.year_of(value)
        elif name == "case_diameter_mm":
            normalised = norm.diameter_mm_of(value)
        elif name == "seller_country":
            normalised = _country(value)
        elif name == "declared_condition":
            # Conservée telle que le vendeur l'écrit. Elle n'est pas traduite
            # en note cosmétique : « bon état » n'est pas un constat.
            normalised = None

        if name in ("warranty", "insurance"):
            normalised = _yes_no(value)

        setattr(
            draft,
            name,
            Imported(
                raw=value,
                value=normalised,
                provenance=provenance,
                source=f"caractéristique « {labels[0]} »",
                conflicts=(
                    (f"« {disagreement} » dans la description du vendeur",)
                    if disagreement is not None
                    else ()
                ),
                # La fiche technique sert à **proposer** une valeur ; elle ne
                # prouve pas qu'elle soit juste. Dès qu'une divergence réelle
                # subsiste, c'est à l'utilisateur de trancher.
                needs_confirmation=disagreement is not None,
            ),
        )
        if disagreement is not None:
            warnings.append(
                f"À confirmer — « {labels[0]} » : la fiche technique annonce "
                f"« {value} », la description du vendeur « {disagreement} ». "
                "Les deux sont conservées ; la fiche est proposée par défaut, "
                "sans que cela prouve qu'elle ait raison."
            )

    # Le calibre n'a pas de ligne à lui : le vendeur l'écrit dans la phrase de
    # mouvement. Le mot-clé rend la lecture explicite — ce n'est pas deviner.
    if not draft.calibre.is_present:
        calibre = _CALIBRE_IN_TEXT.search(joined)
        if calibre is not None:
            draft.calibre = Imported(
                raw=calibre.group(0),
                value=calibre.group(1),
                provenance=provenance,
                source="calibre déclaré dans la description",
                # Déclaré par le vendeur au fil d'une phrase, pas dans un champ
                # structuré : proposé, à vérifier.
                needs_confirmation=True,
            )

    # « Serviced » dit qu'une révision est **affirmée**. Ni date ni preuve ne
    # s'en déduisent : le champ porte la mention, pas un fait établi.
    if not draft.service_history.is_present:
        service = _SERVICE_DECLARED.search(joined)
        if service is not None:
            draft.service_history = Imported(
                raw=service.group(0),
                value="declared",
                provenance=provenance,
                source="révision déclarée par le vendeur, sans date ni preuve",
                needs_confirmation=True,
            )
            warnings.append(
                f"Révision déclarée par le vendeur (« {service.group(0)} ») : "
                "sans date ni justificatif dans l'annonce. À faire confirmer."
            )

    stated = _DIAMETER_IN_TEXT.search(joined)
    if stated is not None and draft.case_diameter_mm.value is not None:
        described = norm.diameter_mm_of(stated.group(0))
        if described is not None and described != draft.case_diameter_mm.value:
            draft.case_diameter_mm = Imported(
                raw=draft.case_diameter_mm.raw,
                value=draft.case_diameter_mm.value,
                provenance=draft.case_diameter_mm.provenance,
                source=draft.case_diameter_mm.source,
                conflicts=(f"{described} mm dans la description du vendeur",),
                needs_confirmation=True,
            )
            warnings.append(
                f"À confirmer — diamètre : la fiche annonce "
                f"{draft.case_diameter_mm.value} mm, la description "
                f"{described} mm. Les deux sont conservés ; la fiche est "
                "proposée par défaut, sans que cela prouve qu'elle ait raison."
            )

    if draft.declared_condition.raw:
        warnings.append(
            f"État déclaré par le vendeur : « {draft.declared_condition.raw} ». "
            "C'est une déclaration, pas un constat : à vérifier sur les photos."
        )
    if draft.reference.raw:
        warnings.append(
            f"Référence « {draft.reference.raw} » lue dans l'annonce : elle "
            "reste à confirmer, elle n'est pas vérifiée."
        )

    # --- Boîte et papiers, séparément ---------------------------------------
    box = _yes_no(find_value(lines, _BOX_LABELS)[0])
    papers = _yes_no(find_value(lines, _PAPERS_LABELS)[0])
    draft.box = (
        Imported(raw=None, value=box, provenance=provenance, source="ligne « boîte »")
        if box is not None
        else absent("la fiche ne mentionne pas la boîte")
    )
    draft.papers = (
        Imported(
            raw=None, value=papers, provenance=provenance, source="ligne « papiers »"
        )
        if papers is not None
        else absent("la fiche ne mentionne pas les papiers")
    )

    # --- Enchère en cours ---------------------------------------------------
    bid_line = _find_labelled(lines, _BID_LABELS)
    bid_amount, bid_currency = _money(bid_line) if bid_line else (None, None)
    if bid_amount is not None and bid_currency is not None:
        draft.current_bid_amount = Imported(
            raw=bid_line,
            value=bid_amount,
            provenance=provenance,
            source="enchère en cours affichée",
        )
        draft.current_bid_currency = Imported(
            raw=bid_currency,
            value=bid_currency,
            provenance=provenance,
            source="enchère en cours affichée",
        )
        # La nature du prix est explicite, et c'est le point : une enchère en
        # cours n'est ni un prix demandé, ni un prix d'achat garanti, ni un
        # prix final. Elle monte, et elle peut ne pas atteindre la réserve.
        draft.price_kind = Imported(
            raw="enchère en cours",
            value="current_bid",
            provenance=provenance,
            source="nature du montant, lue sur l'annonce",
        )
        # Le même montant sert de prix du dossier, **avec sa nature**. Le
        # schéma distingue `current_bid` de `asking`, `hammer` et `realized` :
        # l'enregistrer sans le dire ferait calculer une marge sur un montant
        # qui n'existera peut-être jamais.
        draft.price_amount = draft.current_bid_amount
        draft.price_currency = draft.current_bid_currency
        warnings.append(
            f"Montant repris comme **enchère en cours** au "
            f"{draft.fetched_at[:16].replace('T', ' à ')} (UTC). Ce n'est ni "
            "un prix d'achat garanti ni un prix final : il montera."
        )
    else:
        draft.current_bid_amount = absent("enchère en cours non lue")
        draft.current_bid_currency = absent("enchère en cours non lue")
        if bid_line:
            warnings.append(
                "Une ligne d'enchère a été trouvée mais son montant ou sa "
                "devise n'a pas pu être lu. À saisir à la main."
            )

    count = _BID_COUNT.search(joined)
    draft.bid_count = (
        Imported(
            raw=count.group(0),
            value=int(count.group(1)),
            provenance=provenance,
            source="nombre d'enchères affiché",
        )
        if count
        else absent("nombre d'enchères non affiché")
    )

    # --- Clôture ------------------------------------------------------------
    draft.closing_at, draft.closing_timezone, closing_warnings = _closing(lines, joined)
    warnings.extend(closing_warnings)

    # --- Estimation Catawiki, à part ----------------------------------------
    draft.estimate_low, draft.estimate_high, draft.estimate_currency = _estimate(lines)
    if draft.estimate_low.is_present:
        warnings.append(
            "L'estimation affichée est celle de Catawiki, pas celle de "
            "KAIROS. Elle est conservée à part et n'entre dans aucun calcul."
        )

    # --- Réserve ------------------------------------------------------------
    draft.reserve_status = _reserve(joined)
    if not draft.reserve_status.is_present:
        warnings.append(
            "La page ne dit rien du prix de réserve. L'absence de mention ne "
            "veut pas dire qu'il n'y en a pas."
        )

    # --- Commission acheteur -------------------------------------------------
    fee = _BUYER_FEE.search(joined)
    if fee is not None:
        rate = norm.amount_of(fee.group(1))
        draft.buyer_fee_rate = (
            Imported(
                raw=fee.group(0),
                value=(rate / Decimal(100)) if rate is not None else None,
                provenance=provenance,
                source="commission acheteur affichée",
            )
            if rate is not None
            else absent("commission acheteur illisible")
        )
        fixed = norm.amount_of(fee.group(3)) if fee.group(3) else None
        currency = norm.currency_of(fee.group(2)) if fee.group(2) else None
        draft.buyer_fee_fixed = (
            Imported(
                raw=fee.group(0),
                value=fixed,
                provenance=provenance,
                source="commission acheteur affichée",
            )
            if fixed is not None
            else absent("aucune part fixe annoncée")
        )
        draft.buyer_fee_currency = (
            Imported(
                raw=currency,
                value=currency,
                provenance=provenance,
                source="commission acheteur affichée",
            )
            if currency is not None
            else absent("devise de la commission non annoncée")
        )
        warnings.append(
            f"Commission acheteur relevée **sur ce lot** : {fee.group(0)}. "
            "C'est une observation datée, pas une grille de plateforme : elle "
            "ne remplace pas celle du portefeuille et n'est pas ajoutée aux "
            "frais de l'analyse."
        )

    # --- Livraison ----------------------------------------------------------
    (
        draft.shipping_cost_amount,
        draft.shipping_cost_currency,
        draft.shipping_destination,
        shipping_warning,
    ) = _shipping_to_france(lines)
    if shipping_warning:
        warnings.append(shipping_warning)

    # --- Vendeur ------------------------------------------------------------
    seller = _find_labelled(lines, _SELLER_LABELS)
    draft.seller_name = _imported(seller, seller, "vendeur affiché", provenance)

    # Catawiki n'étiquette pas le pays du vendeur : il l'écrit en clair dans
    # le bloc vendeur, et donne séparément « Ships from XX ». On lit les deux,
    # en préférant le pays du vendeur à celui de l'expédition — « Ships from
    # EU » n'est pas un pays.
    if not draft.seller_country.is_present:
        draft.seller_country = _seller_country(lines)

    if _PROFESSIONAL.search(joined):
        draft.seller_type = Imported(
            raw="professional seller",
            value="professional",
            provenance=provenance,
            source="mention explicite d'un vendeur professionnel",
        )
    since = _SELLER_SINCE.search(joined)
    draft.seller_since = (
        Imported(
            raw=since.group(0),
            value=int(since.group(1)),
            provenance=provenance,
            source="ancienneté affichée",
        )
        if since
        else absent("ancienneté du vendeur non affichée")
    )

    # --- Titre et description ------------------------------------------------
    # Le titre n'est pas la première ligne du collage : celle-ci est du
    # chrome de navigation (« Search for brand, model, artist… »). Le vrai
    # titre est la première ligne qui commence par la marque et porte les
    # tirets du gabarit Catawiki. Sans marque connue, on préfère l'absence à
    # un morceau de menu.
    title = _title_line(lines, draft.brand.value)
    draft.title = (
        Imported(
            raw=title,
            value=title,
            provenance=provenance,
            source="ligne de titre du lot",
        )
        if title
        else absent("titre non identifié dans le texte collé")
    )

    # La description du vendeur est une **section**. Recopier tout le collage
    # y ferait entrer le menu, l'historique des enchères et les autres lots du
    # vendeur — du bruit qui noierait ce que le vendeur a réellement écrit.
    body = _seller_description(lines) or joined
    description, serial_seen = strip_serials(body)
    draft.description = (
        Imported(
            raw=description[:8000],
            value=description[:8000],
            provenance=provenance,
            source="description du vendeur",
        )
        if description
        else absent("description non trouvée")
    )
    if serial_seen:
        warnings.append(
            "L'annonce mentionne un numéro de série. Il n'a pas été importé : "
            "les numéros de série restent privés."
        )

    # Le copier-coller du texte visible ne transporte pas les images. Le dire
    # plutôt que de laisser croire qu'il n'y avait pas de photos.
    warnings.append(
        "Les photos ne sont pas reprises : un copier-coller de texte ne les "
        "transporte pas. Elles restent consultables sur Catawiki par le lien."
    )

    draft.warnings = tuple(dict.fromkeys(warnings))
    return draft


def _seller_country(lines: list[str]) -> Imported:
    """Pays du vendeur, lu dans son bloc.

    Deux sources, dans cet ordre : un nom de pays écrit en clair après
    « Sold by », puis « Ships from XX ». La seconde est un repli — le pays
    d'expédition n'est pas celui du vendeur, et « Ships from EU » n'est pas
    un pays du tout.
    """

    start: int | None = None
    for index, line in enumerate(lines):
        if _label_of(line) in _SELLER_LABELS:
            start = index
            break
    window = lines[start : start + 12] if start is not None else lines

    for line in window:
        code = _COUNTRY_NAMES.get(line.strip().lower())
        if code is not None:
            return Imported(
                raw=line,
                value=code,
                provenance=Provenance.ASSISTED,
                source="pays affiché dans le bloc vendeur",
            )

    for line in window:
        shipped = _SHIPS_FROM.match(line.strip())
        # « EU » est une zone, pas un pays : on ne la retient pas.
        if shipped is not None and shipped.group(1).upper() != "EU":
            return Imported(
                raw=line,
                value=shipped.group(1).upper(),
                provenance=Provenance.ASSISTED,
                source="pays d'expédition affiché",
            )

    return absent("pays du vendeur non affiché")
