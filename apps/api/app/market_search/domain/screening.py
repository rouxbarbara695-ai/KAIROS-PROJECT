"""Contrôle d'identité et de configuration d'une annonce candidate.

Chaque annonce reçoit un verdict et **un motif**, retenue comme écartée : c'est
ce qui permet d'afficher « 14 annonces lues, 3 retenues, 11 écartées » avec la
raison de chacune (CLAUDE.md règle 6), au lieu d'un total sans preuve.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.market_search.domain.candidate import Candidate
from app.market_search.domain.policy import SearchPolicy
from app.market_search.domain.reference import (
    brand_present,
    fold,
    match_reference,
)

# Annonces qui ne sont pas la montre entière, en état de marche, authentique.
# Vocabulaire fr / en / de / it / es / nl : les places de marché sont
# européennes et un titre allemand ne doit pas passer faute de mot-clé.
_NOT_A_COMPLETE_WATCH = re.compile(
    r"\b("
    r"for parts|spares?|spare parts|parts only|pour pieces|pieces detachees|"
    r"a reparer|for repair|not working|non funzionante|per ricambi|"
    r"defekt|ersatzteil\w*|bastler|"
    r"box only|empty box|boite seule|boite vide|nur box|nur schachtel|"
    r"bracelet only|strap only|band only|bracelet seul|armband nur|"
    r"dial only|cadran seul|movement only|mouvement seul|case only|boitier seul|"
    r"manual only|warranty card only|papers only|papiers seuls|"
    r"crystal only|verre seul|links?|maillons?"
    r")\b"
)
_COUNTERFEIT = re.compile(
    r"\b(replica|replique|fake|copie|copy|imitation|nachbau|super clone)\b"
)
# « lot de 3 montres », « 2 watches » : plusieurs objets sous un seul prix.
_MULTIPLE_ITEMS = re.compile(
    r"\b(?:lot|set|lotto|konvolut)\s+(?:of|de|di|von)?\s*\d+\s*(?:watches|montres|"
    r"orologi|uhren|relojes)\b|\b\d+\s*(?:watches|montres|orologi|uhren)\b"
)


@dataclass(frozen=True, slots=True)
class Verdict:
    accepted: bool
    code: str
    detail: str
    warnings: tuple[str, ...] = ()


def _reject(code: str, detail: str) -> Verdict:
    return Verdict(accepted=False, code=code, detail=detail)


def screen(
    candidate: Candidate,
    *,
    brand: str,
    reference: str,
    model: str | None,
    policy: SearchPolicy,
    now: datetime | None = None,
) -> Verdict:
    """Retient ou écarte une annonce. L'ordre des contrôles est celui du risque :
    d'abord « est-ce bien cette montre », ensuite « est-ce un prix utilisable »."""

    now = now or datetime.now(UTC)
    title = candidate.title

    if not match_reference(title, reference).found:
        return _reject(
            "reference_not_stated",
            "La référence exacte ne figure pas dans le titre : annonce voisine, "
            "non substituée.",
        )
    if not brand_present(title, brand):
        return _reject(
            "brand_not_stated",
            "La marque ne figure pas dans le titre : la référence pourrait "
            "appartenir à un autre fabricant.",
        )

    folded = fold(title)
    if _COUNTERFEIT.search(folded):
        return _reject("counterfeit_marker", "Le titre évoque une copie.")
    if _NOT_A_COMPLETE_WATCH.search(folded):
        return _reject(
            "not_a_complete_watch",
            "Pièce détachée, accessoire seul ou montre à réparer.",
        )
    if _MULTIPLE_ITEMS.search(folded):
        return _reject("multiple_items", "Plusieurs montres sous un seul prix.")

    if candidate.amount <= 0:
        return _reject("no_price", "Aucun prix exploitable.")

    warnings: list[str] = []
    if model:
        words = re.findall(r"[a-z0-9]{3,}", fold(model))
        if words and not any(word in folded for word in words):
            warnings.append("model_not_stated")

    if candidate.price_kind == "current_bid":
        if candidate.ends_at is None:
            return _reject(
                "auction_end_unknown",
                "Enchère sans heure de clôture : le prix final est inconnaissable.",
            )
        remaining = candidate.ends_at - now
        if remaining < timedelta(0):
            return _reject("auction_already_ended", "L'enchère est terminée.")
        if remaining > timedelta(hours=policy.auction_max_hours_to_end):
            return _reject(
                "auction_too_early",
                "Enchère loin de sa clôture : la mise actuelle n'est pas un prix.",
            )
        if (candidate.bid_count or 0) < policy.auction_min_bids:
            return _reject(
                "auction_without_bids", "Enchère sans aucune mise : pas de prix."
            )
        warnings.append("current_bid_not_final")

    return Verdict(
        True,
        "accepted",
        "Référence exacte et configuration cohérente.",
        tuple(warnings),
    )
