"""Importer ce module peuple Base.metadata avec toutes les tables — requis
par Alembic (autogenerate/check) et par les tests d'intégration."""

from app.shared.infrastructure.db.models import (  # noqa: F401
    accounts,
    analyses,
    audit,
    jobs,
    listings,
    market,
    operations,
    opportunities,
    platforms,
    portfolio_ledger,
    reference_data,
    strategies,
    watches,
)

__all__ = [
    "accounts",
    "analyses",
    "audit",
    "jobs",
    "listings",
    "market",
    "operations",
    "opportunities",
    "platforms",
    "portfolio_ledger",
    "reference_data",
    "strategies",
    "watches",
]
