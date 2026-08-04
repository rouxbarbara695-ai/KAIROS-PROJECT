"""Politique de limitation des tentatives de connexion (POL-045).

Fonction pure : elle décide, elle ne compte pas. Le comptage appartient à
l'adaptateur, parce qu'il est par nature partagé entre les processus.

Deux compteurs, et c'est délibéré.

**Par adresse IP** — la vraie protection. Un attaquant qui essaie des milliers
de mots de passe vient d'un petit nombre d'adresses, et chaque essai coûte au
serveur un calcul Argon2 volontairement lent : sans plafond, une rafale suffit
à le saturer, même sans jamais trouver le mot de passe.

**Par adresse électronique** — un garde-fou, avec un plafond bien plus haut.
Il ne doit surtout pas verrouiller le compte : KAIROS ne sert qu'un
utilisateur, et une limite serrée par adresse offrirait à n'importe qui le
moyen de l'empêcher d'entrer chez lui en martelant son adresse. Mieux vaut un
attaquant ralenti qu'un propriétaire enfermé dehors.
"""

from __future__ import annotations

from dataclasses import dataclass

# Cinq minutes : assez long pour rendre une attaque par force brute
# inintéressante, assez court pour qu'une faute de frappe répétée ne gâche pas
# la soirée.
WINDOW_SECONDS = 300

# Dix échecs depuis une même adresse IP. Un humain qui se trompe dix fois de
# suite en cinq minutes a besoin de retrouver son mot de passe, pas d'un
# onzième essai.
MAX_FAILURES_PER_IP = 10

# Cinquante échecs sur une même adresse électronique. Volontairement haut :
# ce compteur existe pour freiner une attaque distribuée sur plusieurs IP, pas
# pour fermer la porte au propriétaire du compte.
MAX_FAILURES_PER_EMAIL = 50


@dataclass(frozen=True, slots=True)
class ThrottleVerdict:
    allowed: bool
    retry_after_seconds: int = 0


def evaluate(
    *,
    failures_from_ip: int,
    failures_for_email: int,
    window_seconds: int = WINDOW_SECONDS,
) -> ThrottleVerdict:
    """Autorise ou non une tentative de connexion.

    Le refus est prononcé **avant** toute vérification de mot de passe : sinon
    le calcul Argon2 aurait déjà eu lieu, et la limitation ne protégerait plus
    le serveur de ce qu'elle est censée lui épargner.
    """

    if failures_from_ip >= MAX_FAILURES_PER_IP:
        return ThrottleVerdict(allowed=False, retry_after_seconds=window_seconds)
    if failures_for_email >= MAX_FAILURES_PER_EMAIL:
        return ThrottleVerdict(allowed=False, retry_after_seconds=window_seconds)
    return ThrottleVerdict(allowed=True)
