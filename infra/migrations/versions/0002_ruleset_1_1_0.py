"""Ruleset 1.1.0 : dérogation au plafond d'immobilisation (Q-13).

Un ruleset est immuable. Modifier un calcul crée une nouvelle version plutôt
que de réécrire l'ancienne (CLAUDE.md règle 10) : les analyses déjà publiées
sous 1.0.0 conservent leur barème et restent rejouables à l'identique.

Cette migration dérive 1.1.0 de 1.0.0 en base, sans recopier le barème dans le
code : dupliquer huit cents lignes de JSON garantirait une divergence au
premier ajustement.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_RELIEF = """
{
  "cap": 79,
  "minimum_liquidity": 75,
  "minimum_roi": 0.25,
  "minimum_profit_eur": 400,
  "minimum_valuation_confidence": 70,
  "minimum_evidence_quality": 65
}
"""


def upgrade() -> None:
    op.execute(
        f"""
        insert into rulesets (version, config, checksum_sha256, valid_from)
        select
          '1.1.0',
          jsonb_set(
            config,
            '{{scoring,exceptional_deal_relief}}',
            '{_RELIEF.strip()}'::jsonb,
            true
          ) as config,
          encode(
            digest(
              jsonb_set(
                config,
                '{{scoring,exceptional_deal_relief}}',
                '{_RELIEF.strip()}'::jsonb,
                true
              )::text,
              'sha256'
            ),
            'hex'
          ),
          now()
        from rulesets
        where version = '1.0.0'
        on conflict (version) do nothing;
        """
    )


def downgrade() -> None:
    # 1.0.0 n'est pas touché : il n'y a rien à restaurer, seulement à retirer.
    op.execute("delete from rulesets where version = '1.1.0';")
