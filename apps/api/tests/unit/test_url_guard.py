"""Ce que le serveur refuse d'aller chercher.

Chaque test décrit une manière connue de faire sortir une requête là où elle ne
devrait pas aller. Ce ne sont pas des cas théoriques : `169.254.169.254` livre
les identifiants d'instance chez la plupart des hébergeurs, et un domaine
public qui résout vers `10.0.0.5` est le contournement habituel d'une liste
blanche appliquée sur le seul nom.
"""

from __future__ import annotations

import pytest

from app.collection.domain.url_guard import check_addresses, check_shape
from app.shared.domain.errors import DomainError, ErrorCode

ALLOWED = frozenset({"watchfinder.co.uk"})


def _reason(error: DomainError) -> str:
    assert error.code is ErrorCode.COLLECTOR_NOT_AUTHORIZED
    return str(error.details["reason"])


def test_a_known_host_passes() -> None:
    assert check_shape("https://www.watchfinder.co.uk/watches/x", ALLOWED) == (
        "www.watchfinder.co.uk"
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # `file://` et `gopher://` atteignent des ressources locales ;
        # `http://` livrerait la requête en clair.
        ("file:///etc/passwd", "scheme_not_allowed"),
        ("http://www.watchfinder.co.uk/x", "scheme_not_allowed"),
        # Certains analyseurs se trompent d'hôte en présence d'identifiants :
        # ils lisent `watchfinder.co.uk` là où la connexion ira vers `evil`.
        # Refusé sur la présence d'identifiants, avant même le contrôle de
        # domaine — l'ordre importe peu, les deux verrous tiennent.
        ("https://watchfinder.co.uk:pass@evil.test/x", "credentials_in_url"),
        ("https://user@www.watchfinder.co.uk/x", "credentials_in_url"),
        # Un port arbitraire sur un domaine autorisé sert à balayer les
        # services internes exposés sur cet hôte.
        ("https://www.watchfinder.co.uk:2375/x", "port_not_allowed"),
        # L'adresse de métadonnées d'instance, écrite directement.
        ("https://169.254.169.254/latest/meta-data/", "ip_literal"),
        ("https://127.0.0.1/x", "ip_literal"),
        ("https://[::1]/x", "ip_literal"),
        # Un domaine qui *contient* le domaine autorisé sans en être un
        # sous-domaine.
        ("https://watchfinder.co.uk.evil.test/x", "host_not_allowed"),
        ("https://evil.test/x", "host_not_allowed"),
    ],
)
def test_shapes_that_are_refused(url: str, expected: str) -> None:
    with pytest.raises(DomainError) as raised:
        check_shape(url, ALLOWED)
    assert _reason(raised.value) == expected


def test_a_subdomain_of_an_allowed_host_passes() -> None:
    assert check_shape("https://shop.watchfinder.co.uk/x", ALLOWED) == (
        "shop.watchfinder.co.uk"
    )


def test_a_public_address_passes() -> None:
    check_addresses("www.watchfinder.co.uk", ("104.18.32.1", "2606:4700::1"))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",  # boucle locale
        "10.0.0.5",  # réseau privé
        "192.168.1.10",
        "172.16.0.1",
        "169.254.169.254",  # métadonnées d'instance
        "::1",
        "fd00::1",  # adresse locale unique IPv6
        "0.0.0.0",
    ],
)
def test_internal_addresses_are_refused(address: str) -> None:
    with pytest.raises(DomainError) as raised:
        check_addresses("piege.test", (address,))
    assert _reason(raised.value) == "private_address"


def test_one_internal_address_among_several_is_enough_to_refuse() -> None:
    """Le contournement classique : un nom qui résout vers deux adresses.

    Ne vérifier que la première laisserait passer une requête sur deux — et
    une faille qui ne se déclenche qu'une fois sur deux reste une faille.
    """

    with pytest.raises(DomainError) as raised:
        check_addresses("piege.test", ("104.18.32.1", "10.0.0.5"))
    assert _reason(raised.value) == "private_address"


def test_a_name_without_address_is_refused() -> None:
    with pytest.raises(DomainError) as raised:
        check_addresses("vide.test", ())
    assert _reason(raised.value) == "no_address"
