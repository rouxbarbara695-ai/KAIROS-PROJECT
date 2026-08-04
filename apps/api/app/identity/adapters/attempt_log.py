"""Compteur d'échecs de connexion, adossé à Redis (POL-045, POL-043).

Redis plutôt qu'un compteur en mémoire : un compteur de processus repart à zéro
à chaque redémarrage et à chaque déploiement, ce qui offre à un attaquant un
moyen trivial de le remettre à plat. Il ne tiendrait pas non plus si deux
instances servaient l'application.

C'est aussi le premier usage réel de la dépendance Redis, jusqu'ici démarrée
sans servir à rien (POL-043).

**En cas de panne de Redis, la connexion reste possible.** Un limiteur est un
filet, pas la frontière de sécurité — celle-ci reste le mot de passe. Refuser
toute connexion parce que le compteur est injoignable enfermerait le
propriétaire dehors pour une panne d'infrastructure. La panne est journalisée
pour ne pas passer inaperçue.
"""

from __future__ import annotations

import structlog
from redis.asyncio import Redis

from app.identity.domain.throttle import WINDOW_SECONDS

_logger = structlog.get_logger(__name__)

_PREFIX = "kairos:login-failures"


class LoginAttemptLog:
    """Fenêtre glissante approchée, par incrément avec expiration.

    Une fenêtre exacte demanderait de stocker chaque horodatage ; l'incrément
    avec expiration donne une fenêtre « par tranche », ce qui suffit largement
    pour freiner une force brute et coûte une seule commande par tentative.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(scope: str, value: str) -> str:
        return f"{_PREFIX}:{scope}:{value}"

    async def failures(self, *, ip: str, email: str) -> tuple[int, int]:
        try:
            values = await self._redis.mget(
                self._key("ip", ip), self._key("email", email)
            )
        except Exception:  # noqa: BLE001 — toute panne du compteur se traite pareil
            _logger.warning("login_throttle_unavailable", action="reading")
            return 0, 0

        from_ip, for_email = (int(value or 0) for value in values)
        return from_ip, for_email

    async def record_failure(self, *, ip: str, email: str) -> None:
        """N'enregistre que les **échecs**.

        Une connexion réussie ne consomme rien : compter les tentatives plutôt
        que les échecs punirait l'usage normal.
        """

        try:
            pipeline = self._redis.pipeline()
            for key in (self._key("ip", ip), self._key("email", email)):
                pipeline.incr(key)
                pipeline.expire(key, WINDOW_SECONDS)
            await pipeline.execute()
        except Exception:  # noqa: BLE001
            _logger.warning("login_throttle_unavailable", action="recording")

    async def clear(self, *, ip: str, email: str) -> None:
        """Remet les compteurs à zéro après une connexion réussie.

        Sans cela, quelques fautes de frappe suivies d'une connexion réussie
        laisseraient un budget entamé pour les cinq minutes suivantes.
        """

        try:
            await self._redis.delete(self._key("ip", ip), self._key("email", email))
        except Exception:  # noqa: BLE001
            _logger.warning("login_throttle_unavailable", action="clearing")
