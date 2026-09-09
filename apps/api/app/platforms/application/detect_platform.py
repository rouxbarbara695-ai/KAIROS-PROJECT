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
    "catawiki.fr": "catawiki",
    "vestiairecollective.com": "vestiaire_collective",
    "watchcharts.com": "watchcharts",
    "watchfinder.co.uk": "watchfinder",
    "watchfinder.com": "watchfinder",
    # Les domaines nationaux d'eBay sont listés un à un, et ce n'est pas du
    # zèle : une plateforme non reconnue retombe sur `independent_boutique`,
    # dont le mode d'accès est « tenter la récupération ». Un domaine eBay
    # oublié ferait donc émettre vers eBay une requête que ses conditions
    # d'utilisation interdisent — le silence de la table vaudrait
    # autorisation.
    "ebay.com": "ebay",
    "ebay.fr": "ebay",
    "ebay.co.uk": "ebay",
    "ebay.de": "ebay",
    "ebay.it": "ebay",
    "ebay.es": "ebay",
    "ebay.nl": "ebay",
    "ebay.be": "ebay",
    "ebay.ch": "ebay",
    "ebay.at": "ebay",
    "ebay.ie": "ebay",
    "ebay.pl": "ebay",
    "ebay.ca": "ebay",
    "ebay.com.au": "ebay",
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
