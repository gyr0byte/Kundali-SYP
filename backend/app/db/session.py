"""Database session factory.

# NOTE: All PostgreSQL production connections must use SSL (sslmode=require).
"""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the global SQLAlchemy Engine, creating it if needed."""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.DATABASE_URL
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            _engine = create_engine(url, connect_args=connect_args, poolclass=StaticPool)
        else:
            # Production PostgreSQL must require SSL
            _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the global sessionmaker."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding an isolated database session per request."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()
