"""Redis en mémoire, réduit aux commandes du compteur d'échecs.

Une doublure plutôt qu'un vrai Redis, pour deux raisons.

**Le déterminisme.** Le compteur porte une fenêtre de cinq minutes. Adossée à
un vrai Redis partagé par toute la suite, elle rendrait les tests dépendants
de leur ordre et de leur durée : quelques connexions manquées ailleurs
suffiraient à faire échouer un test de limitation, ou à l'empêcher de voir ce
qu'il vérifie. Chaque test reçoit ici son compteur, vierge.

**La panne, qui est un cas métier.** Le compteur doit laisser passer une
connexion quand Redis est injoignable — un limiteur est un filet, pas la
frontière de sécurité. Cela se vérifie en cassant la doublure ; on ne peut pas
demander à un vrai serveur de tomber au bon moment.

La doublure n'implémente que ce que `LoginAttemptLog` appelle. C'est
volontaire : une doublure plus riche que son usage laisse croire à une
couverture qui n'existe pas.
"""

from __future__ import annotations

from collections.abc import Callable


class FakePipeline:
    """Accumule les commandes et ne les applique qu'à `execute`, comme Redis."""

    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._commands: list[Callable[[], object]] = []

    def incr(self, key: str) -> FakePipeline:
        self._commands.append(lambda: self._redis.increment(key))
        return self

    def expire(self, key: str, seconds: int) -> FakePipeline:
        self._commands.append(lambda: self._redis.set_expiry(key, seconds))
        return self

    async def execute(self) -> list[object]:
        self._redis.fail_if_broken()
        results = [command() for command in self._commands]
        self._commands.clear()
        return results


class FakeRedis:
    def __init__(self, *, broken: bool = False) -> None:
        self.values: dict[str, int] = {}
        self.expirations: dict[str, int] = {}
        self.broken = broken

    def fail_if_broken(self) -> None:
        if self.broken:
            raise ConnectionError("Redis injoignable (doublure de test)")

    def increment(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def set_expiry(self, key: str, seconds: int) -> bool:
        self.expirations[key] = seconds
        return True

    async def mget(self, *keys: str) -> list[str | None]:
        self.fail_if_broken()
        # `decode_responses=True` côté client : Redis rend des chaînes, jamais
        # des entiers. La doublure ment moins en rendant la même chose.
        return [
            None if key not in self.values else str(self.values[key]) for key in keys
        ]

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    async def delete(self, *keys: str) -> int:
        self.fail_if_broken()
        removed = 0
        for key in keys:
            self.expirations.pop(key, None)
            if self.values.pop(key, None) is not None:
                removed += 1
        return removed
