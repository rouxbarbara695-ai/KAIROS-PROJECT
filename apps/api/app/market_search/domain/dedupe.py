"""Déduplication : la même montre n'est comptée qu'une fois.

Deux annonces sont la même montre reprise si elles portent la même référence,
le même prix et le même pays, et un titre équivalent une fois la ponctuation et
la casse neutralisées. C'est le cas d'une annonce republiée (nouvel identifiant,
même objet) et d'une montre reprise sur plusieurs places de marché.

Faute de pseudonyme de vendeur — volontairement non conservé — cette clé est le
seul moyen de repérer un doublon ; elle peut manquer un doublon dont le prix a
changé, jamais fusionner deux montres différentes de même prix, de même pays et
de même titre… sauf à en avoir vraiment deux identiques en vente, ce qui reste
compté une fois : le biais est du côté de la prudence.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.market_search.domain.candidate import Candidate
from app.market_search.domain.reference import compact


def dedupe_key(candidate: Candidate) -> str:
    return "|".join(
        (
            compact(candidate.title),
            format(candidate.amount.normalize(), "f"),
            candidate.currency,
            (candidate.country or "").upper(),
            candidate.price_kind,
        )
    )


@dataclass(frozen=True, slots=True)
class Deduplicated:
    kept: list[Candidate]
    duplicates: list[tuple[Candidate, Candidate]]  # (doublon, conservée)


def deduplicate(candidates: list[Candidate]) -> Deduplicated:
    """Garde la première occurrence, la plus fraîche à égalité d'observation."""

    kept: dict[str, Candidate] = {}
    duplicates: list[tuple[Candidate, Candidate]] = []
    for candidate in candidates:
        key = dedupe_key(candidate)
        first = kept.get(key)
        if first is None:
            kept[key] = candidate
        elif first.external_id == candidate.external_id:
            # Même annonce lue par deux requêtes : pas un doublon, une redite.
            continue
        else:
            duplicates.append((candidate, first))
    return Deduplicated(kept=list(kept.values()), duplicates=duplicates)
