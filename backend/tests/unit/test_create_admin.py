"""Unit tests for create_admin CLI script."""

import os
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.permissions import UserRole
from app.db.base import Base
from app.db.models import User
from scripts.create_admin import create_admin_user


@pytest.fixture
def db_session() -> Session:
    """Isolated SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_create_admin_success(db_session: Session) -> None:
    """Creates admin user with ADMIN role and active status."""
    admin = create_admin_user(
        db=db_session,
        email="superadmin@example.com",
        password="SuperAdminSecurePass2026!",
        for_testing=True,
    )
    assert admin.email == "superadmin@example.com"
    assert admin.role == UserRole.ADMIN
    assert admin.is_active is True

    # Check persistence
    saved = db_session.scalar(select(User).where(User.email == "superadmin@example.com"))
    assert saved is not None
    assert saved.role == UserRole.ADMIN


def test_create_admin_weak_password_fails(db_session: Session) -> None:
    """Weak password rejected with ValueError."""
    with pytest.raises(ValueError, match="Password must be at least 10"):
        create_admin_user(
            db=db_session,
            email="admin@example.com",
            password="short",
            for_testing=True,
        )


def test_create_admin_existing_user_promoted(db_session: Session) -> None:
    """If user already exists as regular user, create_admin promotes them to ADMIN."""
    user = User(email="promoted@example.com", password_hash="oldhash", role=UserRole.USER)
    db_session.add(user)
    db_session.commit()

    admin = create_admin_user(
        db=db_session,
        email="promoted@example.com",
        password="NewAdminPassword2026!",
        for_testing=True,
    )
    assert admin.role == UserRole.ADMIN
