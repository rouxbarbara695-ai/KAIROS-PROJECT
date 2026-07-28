from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """Utilisateur authentifié pour la requête courante. En V1 locale
    (Q-01), un seul principal de développement est résolu depuis la
    configuration ; l'adaptateur d'authentification réel viendra plus tard
    sans changer cette forme."""

    user_id: uuid.UUID
    portfolio_ids: frozenset[uuid.UUID]

    def owns_portfolio(self, portfolio_id: uuid.UUID) -> bool:
        return portfolio_id in self.portfolio_ids
