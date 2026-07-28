from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.shared.domain.errors import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class Ruleset:
    """Accès typé à un ruleset immuable et versionné (CLAUDE.md règle 10).

    Aucune valeur n'est codée en dur ni assortie d'un défaut : une constante
    absente est une erreur de configuration, pas une occasion de deviner. Les
    moteurs consomment cet objet et restent ainsi des fonctions pures.
    """

    version: str
    config: dict[str, Any]
    # Texte JSON d'origine. Le conserver permet de figer un instantané fidèle
    # sans repasser par une sérialisation : `Decimal` n'est pas sérialisable en
    # JSON, et le convertir en flottant détruirait la précision du barème.
    raw_config: str = ""

    def _lookup(self, path: tuple[str, ...]) -> Any:
        current: Any = self.config
        for key in path:
            if not isinstance(current, dict) or key not in current:
                raise DomainError(
                    ErrorCode.RULESET_MISSING,
                    f"Constante absente du ruleset {self.version} : {'.'.join(path)}.",
                    details={"ruleset_version": self.version, "path": list(path)},
                )
            current = current[key]
        return current

    def decimal(self, *path: str) -> Decimal:
        value = self._lookup(path)
        if isinstance(value, Decimal):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return Decimal(value)
        raise DomainError(
            ErrorCode.RULESET_MISSING,
            f"Constante non numérique dans le ruleset {self.version} : "
            f"{'.'.join(path)}.",
            details={"ruleset_version": self.version, "path": list(path)},
        )

    def integer(self, *path: str) -> int:
        value = self._lookup(path)
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            raise DomainError(
                ErrorCode.RULESET_MISSING,
                f"Constante non entière dans le ruleset {self.version} : "
                f"{'.'.join(path)}.",
                details={"ruleset_version": self.version, "path": list(path)},
            )
        return int(value)

    def value(self, *path: str) -> Any:
        """Valeur brute, pour les structures que les accesseurs typés ne
        couvrent pas — les courbes de score, listes de paires."""

        return self._lookup(path)

    def mapping(self, *path: str) -> dict[str, Any]:
        value = self._lookup(path)
        if not isinstance(value, dict):
            raise DomainError(
                ErrorCode.RULESET_MISSING,
                f"Section absente du ruleset {self.version} : {'.'.join(path)}.",
                details={"ruleset_version": self.version, "path": list(path)},
            )
        return value

    def decimal_in(self, section: tuple[str, ...], key: str) -> Decimal:
        """Constante indexée par une valeur de vocabulaire.

        Sépare la section — connue à l'écriture du moteur — de la clé, qui
        vient de la donnée : un vocabulaire élargi sans mise à jour du ruleset
        échoue explicitement au lieu de retomber sur une valeur arbitraire.
        """

        return self.decimal(*section, key)
