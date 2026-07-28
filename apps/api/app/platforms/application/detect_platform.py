from __future__ import annotations

from urllib.parse import urlsplit

# Association hôte -> code plateforme, purement technique (routage d'une URL
# vers sa fiche `platforms`) : ce n'est pas une règle métier chiffrée, donc
# pas soumise à CLAUDE.md règle 1. Toute plateforme non reconnue tombe sur
# `independent_boutique`, cohérent avec platform-rules.md.
_HOST_TO_PLATFORM_CODE: dict[str, str] = {
    "chrono24.com": "chrono24",
    "chrono24.fr": "chrono24",
    "catawiki.com": "catawiki",
    "vestiairecollective.com": "vestiaire_collective",
    "watchcharts.com": "watchcharts",
    "watchfinder.co.uk": "watchfinder",
    "watchfinder.com": "watchfinder",
}

_FALLBACK_PLATFORM_CODE = "independent_boutique"


def detect_platform_code(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if host.startswith("www."):
        host = host[len("www.") :]
    for known_host, code in _HOST_TO_PLATFORM_CODE.items():
        if host == known_host or host.endswith("." + known_host):
            return code
    return _FALLBACK_PLATFORM_CODE
