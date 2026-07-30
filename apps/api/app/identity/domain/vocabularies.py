from __future__ import annotations

from typing import Final

# Vocabulaires fermés du ruleset 1.0.0 (scoring.condition_scores). Ce module
# ne fait qu'appliquer la normalisation ; le barème de points reste dans le
# moteur de score (Epic 3).
#
# Seuls `mechanical` (« unknown ») et `originality` (« uncertain ») possèdent
# une case dédiée à l'absence de donnée. `cosmetic` et `completeness` n'en ont
# pas dans le ruleset 1.0.0 : une valeur absente y retombe sur le niveau le
# plus prudent plutôt que sur une hypothèse favorable (principles.md #6),
# ce qui est un choix explicite et documenté, pas un défaut implicite.
MECHANICAL_CONDITIONS: Final = ("verified", "functional", "unknown", "defect")
MECHANICAL_FALLBACK: Final = "unknown"

COSMETIC_CONDITIONS: Final = ("excellent", "very_good", "good", "fair", "poor")
COSMETIC_FALLBACK: Final = "poor"

COMPLETENESS_LEVELS: Final = ("full_set", "box_or_papers", "watch_only")
COMPLETENESS_FALLBACK: Final = "watch_only"

ORIGINALITY_LEVELS: Final = ("original", "uncertain", "major_modification")
ORIGINALITY_FALLBACK: Final = "uncertain"

SELLER_TYPES: Final = ("private", "professional", "unknown")
SELLER_TYPE_FALLBACK: Final = "unknown"

# Vocabulaires du vendeur, lus par la porte « risque vendeur » et par le
# pilier « qualité des preuves ».
#
# `reliability` et `risk_level` ont chacun une case « inconnu » : c'est un
# état réel du dossier, pas un défaut de saisie, et le barème lui donne sa
# propre note. `protections` n'en a pas — l'absence de protection connue
# retombe donc sur « none », le niveau le plus prudent. Supposer une
# protection qu'on n'a pas constatée serait exactement l'erreur que
# principles.md #6 interdit.
SELLER_RELIABILITY_LEVELS: Final = (
    "verified",
    "strong_history",
    "unknown",
    "negative_signals",
)
SELLER_RELIABILITY_FALLBACK: Final = "unknown"

SELLER_RISK_LEVELS: Final = ("low", "medium", "high", "unknown")
SELLER_RISK_FALLBACK: Final = "unknown"

TRANSACTION_PROTECTIONS: Final = (
    "authentication_and_escrow",
    "one_protection",
    "limited_recourses",
    "none",
)
TRANSACTION_PROTECTIONS_FALLBACK: Final = "none"


def normalize(raw_value: str | None, allowed: tuple[str, ...], fallback: str) -> str:
    """Convertit une saisie libre en valeur du vocabulaire fermé. Une valeur
    absente ou non reconnue devient `fallback` — jamais une valeur par défaut
    favorable — mais la saisie brute doit être conservée par l'appelant
    (`watches.raw_input`), jamais perdue (FR-004)."""

    if raw_value is not None:
        candidate = raw_value.strip().lower().replace(" ", "_").replace("-", "_")
        if candidate in allowed:
            return candidate
    return fallback


def completeness_level(box: bool | None, papers: bool | None) -> str:
    """Dérive le niveau de complétude depuis boîte/papiers. L'absence des
    deux champs (jamais renseignés) retombe sur `COMPLETENESS_FALLBACK` ;
    boîte et papiers explicitement `False` produit aussi `watch_only`, ce qui
    est la même valeur mais une saisie différente — conservée séparément
    dans `raw_input` par l'appelant."""

    if box is None and papers is None:
        return COMPLETENESS_FALLBACK
    if box and papers:
        return "full_set"
    if box or papers:
        return "box_or_papers"
    return "watch_only"
