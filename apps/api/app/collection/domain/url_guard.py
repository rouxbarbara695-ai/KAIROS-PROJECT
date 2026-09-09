"""Ce que le serveur a le droit d'aller chercher, et où.

Une URL fournie par l'utilisateur est une instruction donnée au serveur de se
connecter quelque part. Sans garde-fou, cette instruction atteint le réseau
interne : `http://169.254.169.254/` livre les identifiants d'instance chez la
plupart des hébergeurs, `http://127.0.0.1:5432` parle à PostgreSQL, et un nom
de domaine public peut parfaitement résoudre vers `10.0.0.5`. C'est la faille
dite SSRF, et elle ne se corrige pas en filtrant les chaînes : elle se corrige
en contrôlant **l'adresse IP réellement jointe**, à chaque saut.

Quatre verrous, tous nécessaires :

1. **Schéma et forme** — `https` seulement, aucun identifiant dans l'URL,
   port explicite refusé hors 443.
2. **Domaine autorisé** — une liste blanche. KAIROS connaît les plateformes
   qu'il traite ; aller ailleurs n'est pas une fonctionnalité.
3. **Adresse résolue** — toutes les adresses du nom sont vérifiées, et une
   seule adresse privée suffit à refuser. Vérifier la première seulement
   laisserait passer un nom qui résout vers deux adresses dont une interne.
4. **Chaque redirection** — revalidée comme une URL neuve. Un domaine
   autorisé qui redirige vers `127.0.0.1` est le contournement classique.

La limite de taille et le délai d'attente ne sont pas ici mais dans
l'adaptateur, parce qu'ils s'appliquent pendant la lecture ; ils appartiennent
au même dispositif.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.shared.domain.errors import DomainError, ErrorCode

# Un seul saut de plus qu'un `http` → `https` suivi d'un `www.` : au-delà, une
# chaîne de redirections n'est plus une correction d'adresse.
MAX_REDIRECTS = 3

# Deux mégaoctets. Une fiche d'annonce en fait couramment cinq cents kilo-
# octets ; le double du plus gros cas observé laisse de la marge sans offrir à
# un serveur hostile le moyen de saturer la mémoire du processus.
MAX_BYTES = 2 * 1024 * 1024

# Dix secondes. Au-delà, l'utilisateur attend devant un formulaire vide, et le
# repli par import assisté lui coûtera moins cher que la patience.
TIMEOUT_SECONDS = 10.0

_ALLOWED_SCHEME = "https"
_ALLOWED_PORT = 443


@dataclass(frozen=True, slots=True)
class AllowedTarget:
    """Une cible vérifiée : hôte autorisé, adresses publiques."""

    url: str
    host: str


def _refuse(message: str, reason: str) -> DomainError:
    # `COLLECTOR_NOT_AUTHORIZED` et non `VALIDATION_ERROR` : ce n'est pas une
    # faute de saisie, c'est une destination que KAIROS refuse d'atteindre.
    return DomainError(
        ErrorCode.COLLECTOR_NOT_AUTHORIZED, message, details={"reason": reason}
    )


def _host_is_allowed(host: str, allowed_hosts: frozenset[str]) -> bool:
    return any(
        host == allowed or host.endswith("." + allowed) for allowed in allowed_hosts
    )


def check_shape(url: str, allowed_hosts: frozenset[str]) -> str:
    """Contrôles qui ne demandent aucune résolution. Rend l'hôte."""

    parts = urlsplit(url.strip())

    if parts.scheme.lower() != _ALLOWED_SCHEME:
        raise _refuse(
            "Seules les adresses `https` sont récupérées.", "scheme_not_allowed"
        )

    # `user:mot-de-passe@hôte` : une URL qui porte des identifiants n'a rien à
    # faire dans une récupération publique, et certains analyseurs se trompent
    # d'hôte en leur présence.
    if parts.username is not None or parts.password is not None:
        raise _refuse(
            "Une adresse contenant des identifiants n'est pas récupérée.",
            "credentials_in_url",
        )

    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise _refuse("Adresse sans nom de domaine.", "missing_host")

    if parts.port is not None and parts.port != _ALLOWED_PORT:
        raise _refuse(
            "Seul le port 443 est récupéré.",
            "port_not_allowed",
        )

    # Une adresse IP littérale n'est jamais dans la liste blanche, mais le dire
    # explicitement donne un message utile plutôt qu'un « domaine non
    # autorisé » trompeur.
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise _refuse(
            "Une adresse IP directe n'est pas récupérée : seuls des domaines "
            "connus le sont.",
            "ip_literal",
        )

    if not _host_is_allowed(host, allowed_hosts):
        raise _refuse(
            "Ce domaine ne fait pas partie des plateformes que KAIROS "
            "récupère. Utiliser l'import assisté.",
            "host_not_allowed",
        )

    return host


def check_addresses(host: str, addresses: tuple[str, ...]) -> None:
    """Refuse dès qu'une adresse résolue n'est pas publique.

    **Toutes** les adresses, pas la première : un nom qui résout vers une
    adresse publique et une adresse interne servirait la seconde une fois sur
    deux, et le contrôle passerait un essai sur deux.
    """

    if not addresses:
        raise _refuse(f"Le domaine {host} ne résout vers aucune adresse.", "no_address")

    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:  # pragma: no cover - le résolveur rend des IP
            raise _refuse("Adresse résolue illisible.", "unresolvable") from exc

        # `is_global` est faux pour privé, boucle locale, lien local (dont
        # 169.254.169.254, l'adresse de métadonnées d'instance), multicast et
        # réservé. Une seule condition, et elle ne s'oublie pas par morceaux.
        if not address.is_global:
            raise _refuse(
                "Ce domaine désigne une adresse du réseau interne.",
                "private_address",
            )
