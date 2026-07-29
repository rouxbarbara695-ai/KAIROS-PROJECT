"""Ruleset 1.2.0 : champs de fiche pris en compte par la qualité des preuves.

`scoring-engine.md` définit la qualité de la fiche comme « champs utiles
renseignés / champs applicables » sans énumérer les champs. La liste est donc
une décision, et une décision qui déplace un score appartient à un barème
versionné plutôt qu'à du code (CLAUDE.md règle 10) : autrement, ajouter un
champ au formulaire changerait rétroactivement la note d'analyses déjà
publiées.

La liste retenue est celle du parcours manuel actuel. Elle reste ouverte —
voir Q-14 dans `docs/decisions/open-questions.md`.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_RECORD_FIELDS = """
[
  "brand",
  "reference",
  "reference_status",
  "mechanical_condition",
  "cosmetic_condition",
  "originality",
  "box",
  "papers",
  "price",
  "seller_country",
  "seller_type",
  "platform"
]
"""

_PATCH = f"""
jsonb_set(config, '{{scoring,record_fields}}', '{_RECORD_FIELDS.strip()}'::jsonb, true)
"""


def upgrade() -> None:
    op.execute(
        f"""
        insert into rulesets (version, config, checksum_sha256, valid_from)
        select
          '1.2.0',
          {_PATCH} as config,
          encode(digest(({_PATCH})::text, 'sha256'), 'hex'),
          now()
        from rulesets
        where version = '1.1.0'
        on conflict (version) do nothing;
        """
    )


def downgrade() -> None:
    """Ne retire rien : `rulesets` est append-only par contrat.

    Supprimer un barème publié est précisément ce que le déclencheur
    d'immuabilité empêche, et à raison — toute analyse qui le référence
    perdrait le barème qui l'a produite (CLAUDE.md règles 4 et 10). Un barème
    inutilisé ne coûte rien ; une analyse orpheline serait irréparable.

    La descente reste donc possible sans erreur, et `0001` fait table rase de
    toute façon si l'on descend jusqu'à la base.
    """
