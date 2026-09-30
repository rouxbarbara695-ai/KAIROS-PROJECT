"""Ce que l'annonce dit de la configuration de la montre — relevé, jamais déduit.

Une même référence existe en plusieurs configurations : sur cuir ou sur bracelet
or, en acier ou en or, quartz ou mécanique. Leurs prix diffèrent de plusieurs
milliers d'euros (un Reverso Duetto 266.1.44 sur bracelet or et un sur cuir ne
sont pas la même population). KAIROS ne connaît pas la configuration de la montre
cherchée : il **relève** ici celle de chaque annonce et l'affiche, sans exclure
ni pondérer. Une règle de comparabilité (métal, bracelet, dimensions) est une
décision métier : `open-questions.md`.

Le relevé est une lecture de mots-clés : l'absence d'un mot n'affirme rien.
"""

from __future__ import annotations

import re

from app.market_search.domain.reference import fold

_METALS = (
    ("yellow gold", r"yellow gold|or jaune|gelbgold|oro giallo|18k yellow|18ct yellow"),
    ("pink gold", r"pink gold|rose gold|or rose|roségold|oro rosa"),
    ("white gold", r"white gold|or blanc|weissgold|weißgold|oro bianco"),
    (
        "gold (couleur non précisée)",
        r"\b(18k|18ct|18 carat|750|14k|9ct)\b(?!.*(yellow|pink|rose|white))",
    ),
    ("gold plated", r"gold[- ]plated|plaque or|plaqué or|vermeil|doubl[eé] or"),
    ("steel", r"stainless steel|\bsteel\b|acier|edelstahl|acciaio"),
    ("silver", r"sterling|silver 925|argent 925|\b925\b"),
    ("platinum", r"platinum|platine|platin"),
)
_BRACELET = (
    (
        "bracelet métal",
        r"link bracelet|integrated bracelet|steel bracelet|gold bracelet|bracelet",
    ),
    ("cuir / lanière", r"leather|strap|cuir|crocodile|alligator|lederband"),
)
_MOVEMENT = (
    ("quartz", r"quartz|battery"),
    ("remontage manuel", r"manual[- ]wind|manual winding|remontage manuel|handaufzug"),
    ("automatique", r"automatic|self[- ]winding|automatique|automatik"),
)
_EXTRAS = (
    ("boîte", r"\bbox\b|boite|coffret|scatola"),
    (
        "papiers / garantie",
        r"papers|papiers|warranty|garantie|guarantee|certificate|certificat",
    ),
)


def _found(text: str, table: tuple[tuple[str, str], ...]) -> list[str]:
    return [label for label, pattern in table if re.search(pattern, text)]


def configuration_hints(*texts: str | None) -> dict[str, list[str]]:
    """Mots-clés de configuration présents dans les textes de l'annonce."""

    folded = fold(" ".join(t for t in texts if t))
    hints = {
        "métal": _found(folded, _METALS),
        "bracelet": _found(folded, _BRACELET),
        "mouvement": _found(folded, _MOVEMENT),
        "accessoires": _found(folded, _EXTRAS),
    }
    return {key: values for key, values in hints.items() if values}
