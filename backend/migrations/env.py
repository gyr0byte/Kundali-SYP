"""Alembic migration environment configured for offline and online schema checks."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection

# Ensure `backend/` is importable regardless of current working directory.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.db.base import Base  # noqa: E402
from app.db.connection import postgres_engine, postgres_url  # noqa: E402
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


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode to emit SQL without a DB connection."""
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        output_buffer=config.stdout,
    )

    with context.begin_transaction():
        context.run_migrations()


def migrate(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Use a guarded test connection or the operator's independently selected target."""
    if connection := config.attributes.get("connection"):
        migrate(connection)
        return

    url = postgres_url(os.environ.get("DATABASE_URL", ""), os.environ.get("KUNDALI_DB_CA_FILE"))
    expected = os.environ.get("KUNDALI_DB_MIGRATION_TARGET")
    if not expected or expected != f"{url.host}:{url.port}/{url.database}":
        raise RuntimeError("Online migration target does not match the approved target.")
    engine = postgres_engine(url)
    try:
        with engine.begin() as connection:
            if connection.scalar(text("SELECT current_schema() = 'public'")) is not True:
                raise RuntimeError("Expected the public migration schema.")
            migrate(connection)
    except Exception:
        raise RuntimeError(
            "Online migration failed. Inspect the approved database privately."
        ) from None
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
