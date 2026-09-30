"""Correspondance de référence : exacte, avec des variantes d'écriture prouvées.

Le moteur traite tout comparable rattaché à une référence comme **identique** à
la montre cherchée (`compute_valuation._assess`, `reference_match="same"`). Une
référence voisine glissée ici fausserait donc la cote sans que rien ne le
signale. La règle est donc stricte : mieux vaut manquer une annonce qu'en
retenir une qui n'est pas la bonne.

Une variante d'écriture n'est admise que si elle ne change que la **ponctuation
ou la casse** : « 1561.61.00 », « 1561 61 00 », « 1561-61-00 » et « 15616100 » sont
la même référence. Retirer une lettre ou un groupe de chiffres n'en est pas une :
« 1002253 » sans son « W » n'est pas « W1002253 », et « 1561.61 » n'est pas
« 1561.61.00 ».
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Un séparateur d'écriture : blanc, point, tiret, tiret bas, barre oblique.
_SEPARATOR = r"[\s.\-_/]?"

# Alias de marque reconnus. Une marque écrite autrement que son nom courant est
# une variante d'écriture de la même marque, pas une autre marque.
_BRAND_ALIASES: dict[str, tuple[str, ...]] = {
    "jaegerlecoultre": ("jaegerlecoultre", "jaeger", "jlc"),
    "iwc": ("iwc", "internationalwatchco", "iwcschaffhausen"),
    "audemarspiguet": ("audemarspiguet", "audemars", "ap"),
    "vacheronconstantin": ("vacheronconstantin", "vacheron"),
    "patekphilippe": ("patekphilippe", "patek"),
    "tagheuer": ("tagheuer", "heuer"),
    "panerai": ("panerai", "officinepanerai"),
}


def fold(text: str) -> str:
    """Minuscules sans accents : « Vendôme » et « vendome » se valent."""

    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower()


def compact(text: str) -> str:
    """Lettres et chiffres seulement, en minuscules sans accents."""

    return re.sub(r"[^a-z0-9]", "", fold(text))


def _groups(reference: str) -> list[str]:
    """Découpe une référence en groupes de chiffres ou de lettres.

    « W1002253 » donne `["W", "1002253"]` : l'annonce peut écrire « W 1002253 »,
    jamais « 1002253 » seul.
    """

    return re.findall(r"[A-Za-z]+|\d+", fold(reference))


@dataclass(frozen=True, slots=True)
class ReferenceMatch:
    found: bool
    evidence: str | None = None


def reference_pattern(reference: str) -> re.Pattern[str]:
    groups = _groups(reference)
    if not groups:
        raise ValueError("Une référence vide ne peut pas servir de critère.")
    body = _SEPARATOR.join(re.escape(group) for group in groups)
    return re.compile(
        # Rien d'alphanumérique avant, ni un chiffre suivi d'un point (« 3.1561… ») ;
        # rien d'alphanumérique après, ni un point suivi d'un chiffre
        # (« 1561.61.00.5 » est une autre référence).
        rf"(?<![a-z0-9])(?<!\d\.)({body})(?![a-z0-9])(?!\.\d)",
    )


def match_reference(text: str, reference: str) -> ReferenceMatch:
    found = reference_pattern(reference).search(fold(text))
    return (
        ReferenceMatch(found=True, evidence=found.group(1))
        if found
        else (ReferenceMatch(found=False))
    )


def spelling_variants(reference: str) -> tuple[str, ...]:
    """Écritures de la référence à essayer dans une recherche.

    Uniquement des variantes de ponctuation : c'est ce que `match_reference`
    accepte, ni plus ni moins. Une source qui ne trouve que la forme pointée
    trouvera l'autre avec la forme compacte.
    """

    groups = _groups(reference)
    if not groups:
        return ()
    raw = reference.strip()
    variants = [raw, "".join(groups), " ".join(groups), ".".join(groups)]
    seen: dict[str, None] = {}
    for variant in variants:
        seen.setdefault(variant.upper() if variant.isalpha() else variant, None)
    return tuple(seen)


def brand_present(text: str, brand: str) -> bool:
    """La marque, ou un alias reconnu, figure dans le texte."""

    haystack = compact(text)
    wanted = compact(brand)
    if not wanted:
        return False
    aliases = _BRAND_ALIASES.get(wanted, (wanted,))
    return any(alias in haystack for alias in aliases)
