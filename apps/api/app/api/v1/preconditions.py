"""`ETag` et `If-Match` : la protection des modifications concurrentes.

Le problème qu'elle résout est banal et silencieux. Deux onglets ouvrent la
même fiche. L'un corrige l'état de la montre, l'autre corrige le vendeur. Le
second enregistre en dernier et écrase la correction du premier sans que rien
ne l'annonce — ni à celui qui écrase, ni à celui dont le travail disparaît.

La réponse expose donc la version du dossier (`ETag`), et une correction doit
dire sur quelle version elle s'appuie (`If-Match`). Si la version a bougé,
l'écriture est refusée : la saisie est conservée côté client, qui propose de
recharger.

**La garantie ne tient pas dans ce module.** Ce qui est ici est un contrôle
préalable, utile pour rendre une erreur claire et éviter du travail inutile.
La garantie réelle est le `where version = …` que l'ORM ajoute à chaque
`UPDATE` d'opportunité (`version_id_col`) : entre une comparaison en Python et
l'écriture, une transaction concurrente passerait.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import Header, Response

from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.versioning import check_version

__all__ = ["IfMatch", "check_version", "etag_for", "required_version", "tag"]

IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description=(
            "Version du dossier sur laquelle s'appuie la correction, telle que "
            "l'`ETag` de la dernière lecture l'a donnée. Obligatoire sur les "
            "corrections : sans elle, deux modifications concurrentes "
            "s'écraseraient en silence."
        ),
    ),
]

_ETAG = re.compile(r'^(?:W/)?"version-(\d+)"$')


def etag_for(version: int) -> str:
    return f'"version-{version}"'


def tag(response: Response, version: int) -> None:
    response.headers["ETag"] = etag_for(version)


def required_version(value: str | None) -> int:
    """Version exigée par l'appelant, ou une erreur explicite.

    L'en-tête est **obligatoire** ici, et son absence est une erreur plutôt
    qu'un laissez-passer : accepter une correction qui ne dit pas sur quoi elle
    s'appuie, c'est exactement le comportement que cette protection remplace.
    """

    if value is None or not value.strip():
        raise DomainError(
            ErrorCode.RESOURCE_VERSION_CONFLICT,
            "`If-Match` est obligatoire sur une correction : indiquer la "
            "version lue, telle que l'`ETag` de la réponse l'a donnée.",
            details={"reason": "if_match_required"},
        )

    # `*` signifie « n'importe quelle version » : c'est précisément
    # l'écrasement aveugle qu'on refuse.
    matched = _ETAG.match(value.strip())
    if matched is None:
        raise DomainError(
            ErrorCode.VALIDATION_ERROR,
            'Forme attendue pour `If-Match` : "version-<entier>".',
            field="If-Match",
        )

    return int(matched.group(1))
