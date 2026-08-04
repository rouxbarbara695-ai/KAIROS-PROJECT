"""Authentification réelle : mots de passe et sessions (POL-040).

Jusqu'ici l'utilisateur était créé à la volée depuis une adresse en
configuration. C'était commode tant que KAIROS tournait sur un poste, et
c'était une porte ouverte dès la première mise en ligne : n'importe qui
connaissant l'URL entrait dans le portefeuille.

Deux ajouts.

`users.password_hash` porte une empreinte Argon2id. Nulle par défaut, y compris
sur les comptes existants : un compte sans mot de passe ne peut pas se
connecter, ce qui est le bon comportement pour le mandataire de développement
que cette migration laisse derrière elle.

`user_sessions` porte des sessions opaques et révocables. Le jeton n'y est
jamais stocké — seule son empreinte l'est — de sorte qu'une base lue par un
tiers ne lui donne aucune session utilisable.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table users add column if not exists password_hash text;")
    op.execute(
        """
        create table if not exists user_sessions (
          id uuid primary key default gen_random_uuid(),
          user_id uuid not null references users(id),
          token_fingerprint text not null unique,
          issued_at timestamptz not null default now(),
          expires_at timestamptz not null,
          last_seen_at timestamptz not null default now(),
          revoked_at timestamptz,
          check (expires_at > issued_at),
          check (revoked_at is null or revoked_at >= issued_at)
        );
        create index if not exists user_sessions_user_idx on user_sessions (user_id);
        """
    )


def downgrade() -> None:
    op.execute("drop table if exists user_sessions;")
    op.execute("alter table users drop column if exists password_hash;")
