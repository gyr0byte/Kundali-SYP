"""Alembic migration environment configured for offline and online schema checks."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure `backend/` is importable regardless of current working directory.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.db.base import Base  # noqa: E402
from app.db.models import (  # noqa: E402, F401
    AstrologerProfile,
    AuditLog,
    BirthProfile,
    PasswordResetToken,
    RefreshToken,
    User,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_PLACEHOLDER_URL = "driver://user:pass@localhost/dbname"


def _resolve_database_url(*, offline: bool) -> str:
    """Resolve database URL safely without exposing settings errors in offline mode."""
    configured = config.get_main_option("sqlalchemy.url")
    env_url = os.environ.get("DATABASE_URL")

    if configured and configured != _PLACEHOLDER_URL:
        return configured
    if env_url and env_url.strip():
        return env_url.strip()
    if offline:
        # Dialect-only placeholder URL for `--sql` generation (opens no DB connection).
        return "postgresql+psycopg://"
    raise RuntimeError("DATABASE_URL must be set to run online Alembic migrations.")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode to emit SQL without a DB connection."""
    url = _resolve_database_url(offline=True)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        output_buffer=config.stdout,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a configured SQLAlchemy engine."""
    url = _resolve_database_url(offline=False)
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
