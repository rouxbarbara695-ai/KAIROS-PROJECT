"""Plateforme d'achat d'une opportunité sans annonce.

Une saisie manuelle peut venir de Catawiki sans qu'on ait collé l'URL, et ses
frais d'achat existent quand même. Faute de cette colonne, toute opportunité
manuelle était traitée comme un achat de particulier à particulier — sans
commission — ce qui surestimait le profit de tout achat en plateforme saisi à
la main.

`add column if not exists` parce que `0001` rejoue `database/schema.sql` d'un
bloc : sur une base neuve la colonne existe déjà à l'arrivée ici, sur une base
existante non. C'est la bascule vers les migrations incrémentales que
`POL-046` annonçait.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        alter table opportunities
          add column if not exists purchase_platform_id uuid references platforms(id);
        """
    )


def downgrade() -> None:
    op.execute("alter table opportunities drop column if exists purchase_platform_id;")
