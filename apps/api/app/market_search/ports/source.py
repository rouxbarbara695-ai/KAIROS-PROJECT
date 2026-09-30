"""Port d'une source de comparables.

Une source cherche, elle ne décide de rien : ni de ce qui est retenu, ni de ce
qui devient un comparable. Elle rend des candidats et dit ce qu'elle a
réellement interrogé. Le contrôle d'identité, la déduplication et
l'enregistrement restent en cœur d'application, identiques pour toutes les
sources.
"""

from __future__ import annotations

from typing import Protocol

from app.market_search.domain.candidate import SearchQuery, SourceOutcome


class ComparableSource(Protocol):
    name: str

    def is_configured(self) -> bool:
        """La source peut-elle être interrogée (accès validé et identifiants) ?

        Une source non configurée n'est pas une source en panne : elle n'émet
        aucune requête et le dit.
        """

    async def search(self, query: SearchQuery) -> SourceOutcome:
        """Cherche les annonces actives. Ne lève jamais : tout échec est rendu
        dans `SourceOutcome`, avec son diagnostic."""
