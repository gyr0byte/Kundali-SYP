"""Report PostgreSQL connectivity and readiness without mutating the database."""

import os
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.connection import (  # noqa: E402
    DatabaseConfigurationError,
    DatabaseConnectionError,
    postgres_engine,
    postgres_url,
)

HEAD = "0006_knowledge_corpus"


def inspect_database(engine: Engine) -> tuple[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout = '5s'"))
        if connection.scalar(text("SELECT 1")) != 1:
            raise DatabaseConnectionError("Connectivity probe failed.")
        driver = connection.connection.driver_connection
        if driver is None or not driver.pgconn.ssl_in_use:
            raise DatabaseConnectionError("PostgreSQL did not negotiate TLS.")

        revision = "not migrated"
        if connection.scalar(text("SELECT to_regclass('public.alembic_version') IS NOT NULL")):
            revisions = connection.scalars(text("SELECT version_num FROM public.alembic_version"))
            known = {
                "0001_initial_auth_tables",
                "0002_birth_profiles_table",
                "0003_enable_pgvector",
                "0004_chart_snapshots",
                "0005_resolved_bs_profiles",
                HEAD,
            }
            detected = revisions.all()
            revision = detected[0] if len(detected) == 1 and detected[0] in known else "unknown"

        installed = connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
        available = connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')")
        )
        vector = (
            "installed" if installed else "available, not installed" if available else "unavailable"
        )
        return revision, vector


def main() -> int:
    """Return 0 for ready, 1 for reachable but incomplete, 2 for config, 3 for probe failure."""
    engine = None
    try:
        url = postgres_url(os.environ.get("DATABASE_URL", ""), os.environ.get("KUNDALI_DB_CA_FILE"))
        engine = postgres_engine(url)
        revision, vector = inspect_database(engine)
    except DatabaseConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    except Exception:
        print("PostgreSQL connectivity or inspection failed.", file=sys.stderr)
        return 3
    finally:
        if engine is not None:
            engine.dispose()

    print("PostgreSQL reachable with verified TLS.")
    print(f"Alembic revision: {revision}")
    print(f"pgvector: {vector}")
    return 0 if revision == HEAD and vector == "installed" else 1


if __name__ == "__main__":
    sys.exit(main())
