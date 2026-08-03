"""Crée un compte, ou redéfinit son mot de passe.

    python -m app.create_user ghjuliaclara@gmail.com

Le mot de passe est demandé en invite masquée plutôt que passé en argument :
un argument de ligne de commande figure dans l'historique du shell et dans la
liste des processus de la machine.

C'est le seul chemin de création de compte. Aucune route ne l'expose : KAIROS
est mono-organisation (CLAUDE.md règle 12), et un formulaire d'inscription
ouvert sur un portefeuille personnel serait une porte, pas une fonctionnalité.
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.identity.application.authentication import create_user, revoke_all
from app.shared.config import get_settings
from app.shared.domain.errors import DomainError


async def _run(email: str, password: str) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url.get_secret_value())
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        async with factory() as session:
            user = await create_user(session, email=email, password=password)
            # Un mot de passe changé doit fermer les sessions ouvertes : les
            # laisser vivre viderait le changement de son sens sur un appareil
            # perdu.
            revoked = await revoke_all(session, user.id)
    finally:
        await engine.dispose()

    print(f"Compte prêt : {user.email}")
    if revoked:
        print(f"{revoked} session(s) révoquée(s) par le changement de mot de passe.")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage : python -m app.create_user <adresse>", file=sys.stderr)
        return 2

    password = getpass.getpass("Mot de passe : ")
    if password != getpass.getpass("Confirmation : "):
        print("Les deux saisies diffèrent.", file=sys.stderr)
        return 1

    try:
        return asyncio.run(_run(sys.argv[1], password))
    except DomainError as error:
        print(error.message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
