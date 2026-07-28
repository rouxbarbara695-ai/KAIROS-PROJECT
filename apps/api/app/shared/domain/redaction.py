from __future__ import annotations

from typing import Any

# Source unique des clés à masquer (CLAUDE.md règle 11 ; PRD §6). Utilisée à la
# fois par les logs et par toute réponse API transportant une charge JSON libre
# — typiquement les `before_data`/`after_data` des événements d'audit, que le
# schéma ne contraint pas et qui pourraient donc accueillir n'importe quoi.
SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "token",
        "password",
        "secret",
        "serial_number",
        "serial_number_encrypted",
        "database_url",
        "redis_url",
        "cursor_secret",
    }
)

MASK = "***"


def redact(value: Any) -> Any:
    """Remplace récursivement la valeur de toute clé sensible par `MASK`.

    Le masquage porte sur la clé, jamais sur le contenu : une donnée légitime
    n'est pas altérée, et une clé sensible est neutralisée quelle que soit sa
    profondeur dans la structure.
    """

    if isinstance(value, dict):
        return {
            key: (MASK if str(key).lower() in SENSITIVE_KEYS else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
