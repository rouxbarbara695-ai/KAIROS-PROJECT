"""Mots de passe et jetons de session — fonctions pures.

Aucune de ces fonctions ne connaît FastAPI ni PostgreSQL. Elles décident
seulement de ce qui vaut secret et de comment on le vérifie.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.shared.domain.errors import DomainError, ErrorCode

# Argon2id avec les paramètres par défaut de la bibliothèque, qui suivent les
# recommandations de l'OWASP. Les figer ici plutôt que de les disperser
# garantit qu'un mot de passe reste vérifiable après un changement de réglage :
# `PasswordHasher.verify` relit les paramètres inscrits dans l'empreinte.
_HASHER = PasswordHasher()

# Un secret trop court se casse hors ligne quelle que soit la qualité du
# hachage. Douze caractères est le plancher retenu ; il est configurable nulle
# part à dessein, pour qu'on ne puisse pas l'abaisser par commodité.
MINIMUM_PASSWORD_LENGTH = 12

_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """Empreinte Argon2id d'un mot de passe.

    Le mot de passe lui-même ne doit jamais être stocké, journalisé ni renvoyé.
    L'empreinte porte son propre sel et ses propres paramètres.
    """

    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            f"Le mot de passe doit faire au moins {MINIMUM_PASSWORD_LENGTH} "
            "caractères.",
            field="password",
        )
    return _HASHER.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Vérifie un mot de passe contre son empreinte.

    Un utilisateur sans empreinte ne peut pas se connecter — mais la
    vérification est tout de même effectuée contre une empreinte factice, pour
    que le temps de réponse ne trahisse pas l'existence du compte.
    """

    candidate = password_hash or _ABSENT_HASH
    try:
        return _HASHER.verify(candidate, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Empreinte d'une valeur qui n'est le mot de passe de personne. Elle sert
# uniquement à consommer le même temps de calcul quand le compte n'existe pas :
# sans elle, une réponse instantanée révélerait quelles adresses sont connues.
_ABSENT_HASH = _HASHER.hash(secrets.token_urlsafe(32))


def new_session_token() -> str:
    """Un jeton de session opaque, imprévisible.

    Opaque et non signé : révoquer une session doit être possible, ce qu'un
    jeton auto-porteur interdirait sans tenir par ailleurs une liste de
    révocation — c'est-à-dire sans revenir à une table de sessions.
    """

    return secrets.token_urlsafe(_TOKEN_BYTES)


def fingerprint(token: str) -> str:
    """Ce qu'on stocke d'un jeton : son empreinte, jamais lui.

    Une base lue par un tiers ne doit pas lui donner de sessions utilisables.
    SHA-256 suffit ici, à la différence d'un mot de passe : le jeton est déjà
    long et aléatoire, il n'y a rien à deviner par force brute.
    """

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(candidate_fingerprint: str, stored_fingerprint: str) -> bool:
    """Comparaison à temps constant, pour ne rien apprendre d'un échec."""

    return hmac.compare_digest(candidate_fingerprint, stored_fingerprint)
