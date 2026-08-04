"""Client Redis partagé.

Créé une fois pour l'application. Le pool interne de `redis.asyncio` gère les
connexions ; en ouvrir un par requête coûterait une poignée de main réseau à
chaque tentative de connexion.
"""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis

from app.shared.config import get_settings


@lru_cache
def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=True)
