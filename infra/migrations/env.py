from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Permet d'importer `app.*` quand Alembic est lancé avec
# `-c ../../infra/migrations/alembic.ini` depuis apps/api.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.shared.config import get_settings  # noqa: E402
from app.shared.infrastructure.db.base import Base  # noqa: E402
from app.shared.infrastructure.db import models  # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    # Un `sqlalchemy.url` explicitement fourni (ex. par les tests, via
    # `cfg.set_main_option`) prend le pas sur la configuration applicative —
    # utile pour migrer une base de test isolée sans toucher .env.
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    return get_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
