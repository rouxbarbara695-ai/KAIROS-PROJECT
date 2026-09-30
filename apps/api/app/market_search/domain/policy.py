"""Réglages de la recherche : configurables, versionnés, provisoires.

Aucune de ces valeurs n'est une règle métier de la cote : elles bornent la
**collecte**. Elles sont provisoires, listées dans `open-questions.md`, et la
version est enregistrée avec chaque recherche pour qu'on sache toujours avec
quels réglages un comparable a été retenu.
"""

from __future__ import annotations

from dataclasses import dataclass

POLICY_VERSION = "1.1.0"


@dataclass(frozen=True, slots=True)
class SearchPolicy:
    version: str = POLICY_VERSION
    # Les conditions de l'API eBay limitent l'âge d'une annonce affichée à six
    # heures, sous peine d'en indiquer l'âge : la fraîcheur d'une recherche suit.
    cache_ttl_hours: int = 6
    # Deux actualisations rapprochées n'apprennent rien et consomment le quota.
    min_refresh_minutes: int = 15
    max_requests_per_run: int = 12
    page_size: int = 50
    max_pages_per_query: int = 2
    delay_between_requests_s: float = 0.4
    request_timeout_s: float = 15.0
    # Une enchère loin de sa clôture n'est pas un prix : elle n'est retenue que
    # proche de la fin, et seulement si quelqu'un a déjà enchéri.
    auction_max_hours_to_end: int = 24
    auction_min_bids: int = 1
    # Garde-fou du quota quotidien de la source (5 000 appels par jour pour le
    # programme gratuit eBay) : on s'arrête bien avant.
    daily_request_limit: int = 4000
    # Sources de pages publiques (pas d'API) : politesse et plafonds propres.
    # Le délai réellement appliqué est le plus grand de celui-ci, de celui de la
    # source et du `crawl-delay` de son robots.txt.
    page_source_min_delay_s: float = 3.0
    page_source_max_requests: int = 30
    page_source_max_bytes: int = 3 * 1024 * 1024
    # Pages de résultats lues par requête de recherche, et fiches de détail lues
    # quand la page de résultats ne suffit pas à prouver la référence.
    max_result_pages: int = 3
    max_detail_pages: int = 8
