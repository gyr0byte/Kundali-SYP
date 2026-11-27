"""Connection policy shared by the app, migrations, and diagnostics."""

import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import URL, create_engine, event, make_url
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool


class DatabaseConfigurationError(ValueError):
    """Safe configuration error with no connection details."""


class DatabaseConnectionError(RuntimeError):
    """Safe connection error with no driver details."""


def database_url(value: str) -> URL:
    """Parse a database URL without including its contents in error messages."""
    try:
        return make_url(value)
    except Exception:
        raise DatabaseConfigurationError("Invalid database configuration.") from None


def postgres_url(value: str, ca_file: str | None) -> URL:
    """Build a single-host Psycopg URL with explicit peer verification."""
    url = database_url(value)
    if (
        url.drivername not in {"postgresql", "postgresql+psycopg"}
        or not re.fullmatch(r"[a-zA-Z0-9.-]+", url.host or "")
        or not url.database
        or not url.username
        or not url.password
        or (url.port is not None and not 1 <= url.port <= 65535)
        or not url.query.keys() <= {"sslmode", "channel_binding"}
        or url.query.get("sslmode", "verify-full") != "verify-full"
        or url.query.get("channel_binding", "require") != "require"
        or {"PGSERVICE", "PGHOSTADDR"}.intersection(os.environ)
    ):
        raise DatabaseConfigurationError("Unsupported PostgreSQL connection configuration.")

    try:
        ca = Path(ca_file or "")
        if not ca.is_absolute():
            raise ValueError
        ca = ca.resolve(strict=True)
        if ca.drive.upper() != "D:" or not ca.is_file():
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise DatabaseConfigurationError(
            "Set KUNDALI_DB_CA_FILE to a trusted CA file on D:."
        ) from None

    return url.set(
        drivername="postgresql+psycopg",
        port=url.port or 5432,
        query={
            "sslmode": "verify-full",
            "sslrootcert": str(ca),
            "channel_binding": "require",
            "gssencmode": "disable",
            "connect_timeout": "5",
        },
    )


def postgres_engine(url: URL, *, pooled: bool = False) -> Engine:
    """Create an engine from a policy-validated URL without opening a connection."""
    try:
        engine = create_engine(
            url,
            poolclass=None if pooled else NullPool,
            pool_pre_ping=pooled,
            hide_parameters=True,
            isolation_level="READ COMMITTED",
        )
    except Exception:
        raise DatabaseConfigurationError("Unable to initialize PostgreSQL driver.") from None

    @event.listens_for(engine, "do_connect")
    def connect(dialect: Any, _record: Any, args: list[Any], params: dict[str, Any]) -> Any:
        try:
            connection = dialect.connect(*args, **params)
            if connection.pgconn.ssl_in_use:
                return connection
            connection.close()
        except Exception:
            raise DatabaseConnectionError("PostgreSQL connection failed.") from None
        raise DatabaseConnectionError("PostgreSQL did not negotiate TLS.")

    return engine
