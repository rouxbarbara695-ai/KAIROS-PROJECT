"""Recherche autonome de comparables : une trace par recherche.

Chaque recherche enregistre ce que chaque source a **réellement** fait : requêtes
émises, statut HTTP, candidats lus, retenus, écartés et pourquoi. C'est la
différence entre « 3 comparables trouvés » et une preuve qu'on peut relire.

L'index unique partiel n'autorise qu'une recherche active par référence : deux
clics rapprochés ne doublent ni les requêtes ni le quota de la source.

`if not exists` parce que `0001` rejoue `database/schema.sql` d'un bloc : sur une
base neuve la table existe déjà à l'arrivée ici, sur une base existante non.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists market_search_runs (
          id uuid primary key default gen_random_uuid(),
          portfolio_id uuid not null references portfolios(id),
          opportunity_id uuid not null,
          reference_id uuid not null references watch_references(id),
          requested_by_user_id uuid not null references users(id),
          trigger_kind text not null
            check (trigger_kind in ('reference_confirmed', 'refresh')),
          status job_status not null default 'queued',
          policy_version text not null,
          sources jsonb not null default '[]'::jsonb,
          summary jsonb not null default '{}'::jsonb,
          error_code text,
          error_message text,
          created_at timestamptz not null default now(),
          started_at timestamptz,
          finished_at timestamptz,
          check (
            finished_at is null or started_at is null or finished_at >= started_at
          ),
          constraint market_search_runs_opportunity_same_portfolio_fk
            foreign key (portfolio_id, opportunity_id)
            references opportunities (portfolio_id, id)
        );
        create unique index if not exists market_search_runs_active_uq
          on market_search_runs (portfolio_id, reference_id)
          where status in ('queued', 'running');
        create index if not exists market_search_runs_reference_idx
          on market_search_runs (portfolio_id, reference_id, created_at desc);
        create index if not exists market_search_runs_opportunity_idx
          on market_search_runs (opportunity_id, created_at desc);
        """
    )


def downgrade() -> None:
    op.execute("drop table if exists market_search_runs;")
