from app.identity.domain.throttle import (
    MAX_FAILURES_PER_EMAIL,
    MAX_FAILURES_PER_IP,
    WINDOW_SECONDS,
    evaluate,
)


def test_a_normal_login_is_allowed() -> None:
    verdict = evaluate(failures_from_ip=0, failures_for_email=0)
    assert verdict.allowed
    assert verdict.retry_after_seconds == 0


def test_a_few_typos_do_not_lock_anything() -> None:
    """Se tromper trois fois de mot de passe est ordinaire, pas suspect."""

    assert evaluate(failures_from_ip=3, failures_for_email=3).allowed


def test_the_ip_limit_refuses_at_the_threshold() -> None:
    """Au seuil, pas après : le compteur vaut le nombre d'échecs *déjà*
    enregistrés, donc la tentative en cours serait la onzième."""

    verdict = evaluate(
        failures_from_ip=MAX_FAILURES_PER_IP,
        failures_for_email=0,
    )
    assert not verdict.allowed
    assert verdict.retry_after_seconds == WINDOW_SECONDS


def test_the_email_limit_refuses_at_the_threshold() -> None:
    """Le garde-fou contre une attaque répartie sur beaucoup d'adresses IP :
    aucune d'elles n'atteint son propre seuil, leur somme oui."""

    verdict = evaluate(
        failures_from_ip=0,
        failures_for_email=MAX_FAILURES_PER_EMAIL,
    )
    assert not verdict.allowed
    assert verdict.retry_after_seconds == WINDOW_SECONDS


def test_the_email_limit_is_far_looser_than_the_ip_limit() -> None:
    """Volontaire, et c'est le cœur de l'arbitrage.

    KAIROS ne sert qu'un utilisateur. Une limite serrée par adresse
    électronique donnerait à n'importe qui le moyen de l'enfermer dehors en
    martelant son adresse depuis n'importe où. Mieux vaut un attaquant ralenti
    qu'un propriétaire verrouillé.
    """

    assert MAX_FAILURES_PER_EMAIL > MAX_FAILURES_PER_IP


def test_the_delay_announced_follows_the_window() -> None:
    verdict = evaluate(
        failures_from_ip=MAX_FAILURES_PER_IP,
        failures_for_email=0,
        window_seconds=60,
    )
    assert verdict.retry_after_seconds == 60
