"""Frontière entre KAIROS et le réseau.

Une seule opération, et elle est délibérément pauvre : donner une URL déjà
validée, recevoir du texte. Tout ce qui relève de la politique — domaines
autorisés, redirections, taille, délai — est décidé avant et vérifié par
l'adaptateur ; tout ce qui relève de l'interprétation vient après. Ce port ne
sert qu'à rendre le réseau remplaçable en test, sans quoi la suite dépendrait
d'annonces qui changent tous les jours.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FetchedPage:
    """Ce qu'un serveur distant a rendu.

    `final_url` peut différer de l'URL demandée : chaque redirection a été
    revalidée, et c'est la dernière qui fait foi pour l'identité de l'annonce.
    """

    final_url: str
    status_code: int
    content_type: str
    text: str


class Fetcher(Protocol):
    async def fetch(self, url: str, allowed_hosts: frozenset[str]) -> FetchedPage:
        """Récupère `url`, en refusant tout hôte hors de `allowed_hosts`.

        La liste est passée à chaque appel plutôt que fixée à la construction :
        elle dépend de la plateforme reconnue dans l'URL, donc de l'appel.
        """
        ...
