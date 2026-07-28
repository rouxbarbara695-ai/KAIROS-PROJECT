"""Schéma initial V2 — exécute database/schema.sql tel quel.

Le fichier database/schema.sql est le contrat de référence, déjà vérifié
fonctionnellement sur PostgreSQL 16 réel (extensions, contrainte
d'exclusion temporelle, triggers d'immuabilité, seeds). Plutôt que de
retranscrire à la main 30 tables et leurs contraintes dans des appels
`op.create_table()` — ce qui introduirait un risque de transcription sans
apporter de garantie supplémentaire — cette migration exécute directement
le SQL déjà vérifié, garantissant une fidélité exacte au contrat.

Revision ID: 0001
Revises:
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA_SQL_PATH = Path(__file__).resolve().parents[3] / "database" / "schema.sql"

# Extrait par construction de database/schema.sql (voir infra/migrations/README
# ou `grep -oP '(?<=create table )\w+' database/schema.sql`). Toute nouvelle
# table du contrat doit être ajoutée ici, sous peine de fuite au downgrade.
_TABLES = (
    "users",
    "portfolios",
    "portfolio_members",
    "fx_rates",
    "rulesets",
    "strategies",
    "strategy_versions",
    "platforms",
    "platform_rules",
    "watch_references",
    "watches",
    "sellers",
    "listings",
    "listing_observations",
    "listing_observation_prices",
    "opportunities",
    "opportunity_price_inputs",
    "reference_confirmations",
    "opportunity_events",
    "audit_events",
    "comparables",
    "comparable_overrides",
    "market_valuations",
    "valuation_comparables",
    "analyses",
    "opportunity_costs",
    "purchases",
    "sale_listings",
    "sales",
    "portfolio_ledger_entries",
    "idempotency_records",
    "collection_jobs",
    "alerts",
    "telemetry_events",
)

_FUNCTIONS = (
    "reject_all_mutations",
    "reject_published_analysis_mutation",
    "allow_platform_rule_close_only",
    "touch_opportunity",
    "enforce_authorized_collection_job",
)

_TYPES = (
    "listing_status",
    "price_kind",
    "opportunity_source_mode",
    "opportunity_status",
    "recommendation",
    "source_reliability_level",
    "reference_confirmation_status",
    "gate_status",
    "analysis_state",
    "job_status",
    "cost_status",
    "cost_phase",
    "cost_calculation_mode",
    "cost_basis",
    "cost_kind",
    "platform_access_method",
    "ledger_entry_kind",
)


def upgrade() -> None:
    sql = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    op.execute(sql)


def downgrade() -> None:
    # Ne jamais DROP SCHEMA/CASCADE ici : `alembic_version` vit dans le même
    # schéma, et Alembic doit pouvoir supprimer sa propre ligne de version
    # juste après ce downgrade(). On ne supprime donc que ce que crée
    # upgrade(), jamais la table de suivi d'Alembic.
    op.execute(f"DROP TABLE IF EXISTS {', '.join(_TABLES)} CASCADE;")
    for function_name in _FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {function_name}() CASCADE;")
    for type_name in _TYPES:
        op.execute(f"DROP TYPE IF EXISTS {type_name} CASCADE;")
