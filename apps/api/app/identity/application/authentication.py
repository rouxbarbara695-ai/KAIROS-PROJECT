"""Connexion, résolution de session et déconnexion (POL-040).

Remplace le mandataire de développement, qui créait un utilisateur à la volée
depuis une adresse de configuration : exposé sur Internet, il donnait le
portefeuille à quiconque connaissait l'URL.

Aucune inscription publique. KAIROS est mono-organisation (CLAUDE.md règle
12) : les comptes se créent en ligne de commande, sur la machine qui héberge
la base. Un formulaire d'inscription ouvert sur un portefeuille personnel
serait une porte, pas une fonctionnalité.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.adapters.attempt_log import LoginAttemptLog
from app.identity.domain.credentials import (
    fingerprint,
    hash_password,
    new_session_token,
    verify_password,
)
from app.identity.domain.throttle import evaluate
from app.shared.domain.errors import DomainError, ErrorCode
from app.shared.domain.principal import Principal
from app.shared.infrastructure.db.models.accounts import (
    Portfolio,
    PortfolioMember,
    User,
    UserSession,
)

_DEFAULT_PORTFOLIO_NAME = "Portefeuille par défaut"

# Une session qui expire chaque jour se contourne en notant le mot de passe
# quelque part. Trente jours, révocables à tout moment, tiennent mieux qu'une
# expiration courte qu'on cherche à éviter.
_DEFAULT_LIFETIME = timedelta(days=30)

# Rafraîchir `last_seen_at` à chaque requête écrirait en base sur toute lecture.
# Une granularité à l'heure suffit à distinguer une session vivante d'une
# session oubliée.
_LAST_SEEN_GRANULARITY = timedelta(hours=1)


async def create_user(session: AsyncSession, *, email: str, password: str) -> User:
    """Crée un compte, ou définit le mot de passe d'un compte existant.

    Réservé à l'amorçage en ligne de commande. Aucune route ne l'expose.
    """

    normalised = email.strip().lower()
    if not normalised:
        raise DomainError(ErrorCode.VALIDATION_ERROR, "Adresse requise.", field="email")

    user = (
        await session.execute(select(User).where(User.email == normalised))
    ).scalar_one_or_none()

    if user is None:
        user = User(email=normalised, password_hash=hash_password(password))
        session.add(user)
        await session.flush()
    else:
        user.password_hash = hash_password(password)

    await _ensure_portfolio(session, user)
    await session.commit()
    await session.refresh(user)
    return user


async def _ensure_portfolio(session: AsyncSession, user: User) -> None:
    memberships = (
        (
            await session.execute(
                select(PortfolioMember.portfolio_id).where(
                    PortfolioMember.user_id == user.id
                )
            )
        )
        .scalars()
        .all()
    )
    if memberships:
        return

    portfolio = Portfolio(name=_DEFAULT_PORTFOLIO_NAME)
    session.add(portfolio)
    await session.flush()
    session.add(
        PortfolioMember(portfolio_id=portfolio.id, user_id=user.id, role="owner")
    )
    await session.flush()


async def log_in(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    lifetime: timedelta = _DEFAULT_LIFETIME,
    attempts: LoginAttemptLog | None = None,
    client_ip: str = "inconnue",
) -> str:
    """Vérifie les identifiants et ouvre une session. Retourne le jeton clair.

    Le jeton n'est retourné qu'ici, une seule fois : la base n'en garde que
    l'empreinte, et il n'existe aucun moyen de le relire.

    Adresse inconnue et mot de passe faux donnent la même erreur, et coûtent le
    même temps de calcul. Distinguer les deux dirait à un inconnu quelles
    adresses ont un compte.
    """

    normalised = email.strip().lower()

    # La limite est évaluée **avant** toute vérification : Argon2 est lent par
    # construction, et laisser l'attaquant déclencher ce calcul reviendrait à
    # lui offrir le déni de service que la limitation doit empêcher.
    if attempts is not None:
        from_ip, for_email = await attempts.failures(ip=client_ip, email=normalised)
        verdict = evaluate(failures_from_ip=from_ip, failures_for_email=for_email)
        if not verdict.allowed:
            raise DomainError(
                ErrorCode.RATE_LIMITED,
                "Trop de tentatives de connexion. Réessayez dans quelques minutes.",
                details={"retry_after_seconds": verdict.retry_after_seconds},
            )

    user = (
        await session.execute(select(User).where(User.email == normalised))
    ).scalar_one_or_none()

    if not verify_password(password, None if user is None else user.password_hash):
        if attempts is not None:
            await attempts.record_failure(ip=client_ip, email=normalised)
        raise DomainError(ErrorCode.UNAUTHORIZED, "Adresse ou mot de passe incorrect.")

    assert user is not None  # verify_password échoue toujours sans utilisateur

    token = new_session_token()
    now = datetime.now(UTC)
    session.add(
        UserSession(
            user_id=user.id,
            token_fingerprint=fingerprint(token),
            issued_at=now,
            expires_at=now + lifetime,
            last_seen_at=now,
        )
    )
    await session.commit()

    # Quelques fautes de frappe suivies d'une connexion réussie ne doivent pas
    # amputer le budget des cinq minutes suivantes.
    if attempts is not None:
        await attempts.clear(ip=client_ip, email=normalised)

    return token


async def resolve_session(session: AsyncSession, token: str) -> Principal:
    """Retrouve le mandataire d'un jeton, ou refuse.

    Une session expirée ou révoquée n'est pas distinguée d'un jeton inconnu :
    dans les trois cas, il n'y a rien à faire d'autre que se reconnecter.
    """

    row = (
        await session.execute(
            select(UserSession).where(
                UserSession.token_fingerprint == fingerprint(token)
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise DomainError(ErrorCode.UNAUTHORIZED, "Session invalide ou expirée.")

    if now - row.last_seen_at >= _LAST_SEEN_GRANULARITY:
        row.last_seen_at = now
        await session.commit()

    portfolios = (
        (
            await session.execute(
                select(PortfolioMember.portfolio_id).where(
                    PortfolioMember.user_id == row.user_id
                )
            )
        )
        .scalars()
        .all()
    )

    return Principal(user_id=row.user_id, portfolio_ids=frozenset(portfolios))


async def log_out(session: AsyncSession, token: str) -> None:
    """Révoque une session. Silencieux sur un jeton inconnu : se déconnecter
    d'une session qui n'existe plus n'est pas une erreur."""

    row = (
        await session.execute(
            select(UserSession).where(
                UserSession.token_fingerprint == fingerprint(token)
            )
        )
    ).scalar_one_or_none()

    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await session.commit()


async def revoke_all(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Révoque toutes les sessions d'un utilisateur.

    Utilisé après un changement de mot de passe : garder ouvertes les sessions
    d'un appareil compromis viderait le changement de son sens.
    """

    rows = (
        (
            await session.execute(
                select(UserSession).where(
                    UserSession.user_id == user_id,
                    UserSession.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    for row in rows:
        row.revoked_at = now
    await session.commit()
    return len(rows)
