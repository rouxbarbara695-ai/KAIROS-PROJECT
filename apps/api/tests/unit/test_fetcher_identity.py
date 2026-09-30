"""L'identité que KAIROS présente aux sites qu'il interroge.

Ce test existe à cause d'un défaut que rien d'autre ne pouvait voir : l'agent
contenait des lettres accentuées, `httpx` les refuse dans un en-tête, et le
récupérateur de production n'a jamais pu émettre une seule requête réelle. Tous
les autres tests remplacent le récupérateur par un faux — ils ne touchent pas à
cette bibliothèque.

Ici, on passe par la vraie.
"""

from __future__ import annotations

import httpx

from app.collection.adapters.http_fetcher import USER_AGENT


def test_the_user_agent_is_a_valid_http_header() -> None:
    # Lève UnicodeEncodeError si un caractère n'est pas encodable en ASCII.
    headers = httpx.Headers({"User-Agent": USER_AGENT})
    assert headers["user-agent"] == USER_AGENT


def test_the_user_agent_is_ascii() -> None:
    assert USER_AGENT.isascii()


def test_the_user_agent_names_kairos_honestly() -> None:
    # Se présenter sous son vrai nom : se déguiser en navigateur pour passer un
    # contrôle serait contourner ce contrôle.
    assert USER_AGENT.startswith("KAIROS/")
    assert "Mozilla" not in USER_AGENT
