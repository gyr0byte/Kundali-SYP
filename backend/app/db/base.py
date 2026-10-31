"""SQLAlchemy declarative base and portable type definitions."""

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""

    pass


# Portable JSON type: native JSONB on PostgreSQL, standard JSON elsewhere (e.g. SQLite)
PortableJSON = JSON().with_variant(JSONB(), "postgresql")
