"""Quelle plateforme KAIROS a le droit d'aller chercher, et comment.

Ce module est l'application de la règle 9 de `CLAUDE.md` : aucun accès
automatisé n'est activé sans validation écrite du mode d'accès, des conditions
et de la fréquence. La validation existe (`docs/decisions/open-questions.md`,
Q-04/05/06) et elle est étroite : **une annonce, à la demande de
l'utilisateur**. Aucune surveillance, aucune collecte de masse.

Trois états, et un seul autorise une requête sortante :

- `AUTOMATIC` — la plateforme publie ses fiches sans contrôle d'accès et ses
  conditions ne l'interdisent pas. KAIROS récupère la page.
- `ASSISTED` — la plateforme protège ses pages (défi anti-robot). KAIROS ne
  contourne rien et propose à l'utilisateur de fournir le contenu lui-même.
- `FORBIDDEN` — les conditions d'utilisation de la plateforme interdisent
  l'accès automatisé, qu'il soit techniquement possible ou non. Aucune requête
  n'est émise. C'est le cas d'eBay, dont le `robots.txt` renvoie les
  intégrations à son API officielle sous licence.

La distinction entre `ASSISTED` et `FORBIDDEN` n'est pas cosmétique : la
première est un obstacle technique, la seconde une interdiction. Les traiter
pareil reviendrait à considérer qu'une règle qu'on pourrait enfreindre sans
être vu n'en est pas une.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AccessMode(StrEnum):
    AUTOMATIC = "automatic"
    ASSISTED = "assisted"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True, slots=True)
class PlatformAccess:
    mode: AccessMode
    #: Domaines que le serveur peut joindre pour cette plateforme.
    hosts: frozenset[str]
    #: Dit à l'utilisateur, en clair, pourquoi c'est ainsi.
    explanation: str


_FORBIDDEN_EBAY = PlatformAccess(
    AccessMode.FORBIDDEN,
    frozenset(),
    "eBay interdit l'accès automatisé à ses pages dans ses conditions "
    "d'utilisation et renvoie les intégrations à son API officielle, qui "
    "demande des identifiants développeur. KAIROS n'émet donc aucune requête "
    "vers eBay. Saisir l'annonce à la main, ou coller son contenu.",
)


def _protected(name: str, hosts: set[str]) -> PlatformAccess:
    return PlatformAccess(
        AccessMode.ASSISTED,
        frozenset(hosts),
        f"{name} protège ses pages contre les accès automatisés. KAIROS ne "
        "contourne pas cette protection. Ouvrir l'annonce dans le navigateur "
        "et coller son contenu : l'import assisté lit les mêmes champs.",
    )


# Constaté le 8 septembre 2026 (voir `open-questions.md`). Ce tableau vieillit :
# une protection apparaît ou disparaît, une condition change. Il se corrige en
# le modifiant, pas en le contournant.
_ACCESS: dict[str, PlatformAccess] = {
    "chrono24": _protected("Chrono24", {"chrono24.com", "chrono24.fr"}),
    "catawiki": _protected("Catawiki", {"catawiki.com", "catawiki.fr"}),
    "vestiaire_collective": _protected(
        "Vestiaire Collective", {"vestiairecollective.com"}
    ),
    "ebay": _FORBIDDEN_EBAY,
    "watchfinder": PlatformAccess(
        AccessMode.AUTOMATIC,
        frozenset({"watchfinder.co.uk", "watchfinder.com"}),
        "Watchfinder publie ses fiches en données structurées et son "
        "`robots.txt` les autorise.",
    ),
    "watchcharts": PlatformAccess(
        AccessMode.AUTOMATIC,
        frozenset({"watchcharts.com"}),
        "Page publique, données structurées.",
    ),
}

#: Une boutique indépendante n'a pas de fiche dans ce tableau — il y en a
#: trop, et elles changent. La récupération est tentée : si le site protège
#: ses pages, le refus est constaté à la requête et l'import assisté prend le
#: relais. C'est la seule entrée dont les domaines ne sont pas connus
#: d'avance, et c'est assumé : la garde SSRF ne repose alors plus sur la liste
#: blanche mais sur la vérification des adresses résolues, qui, elle, ne
#: dépend d'aucun tableau.
_INDEPENDENT = PlatformAccess(
    AccessMode.AUTOMATIC,
    frozenset(),
    "Site indépendant : KAIROS tente de lire ses données structurées.",
)


def access_for(platform_code: str) -> PlatformAccess:
    return _ACCESS.get(platform_code, _INDEPENDENT)


def allowed_hosts_for(platform_code: str, host: str) -> frozenset[str]:
    """Domaines joignables pour cette récupération.

    Pour une plateforme connue, sa liste. Pour un site indépendant, le domaine
    demandé lui-même : l'utilisateur a désigné une adresse précise, et les
    redirections restent contraintes à ce domaine — un site indépendant qui
    renvoie ailleurs n'a rien à faire dans un préremplissage.
    """

    access = access_for(platform_code)
    return access.hosts if access.hosts else frozenset({host})
