"""Shared pytest fixtures for unit and integration tests."""

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.dependencies import get_clock, get_db, get_rate_limiter, get_settings
from app.core.permissions import UserRole
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import AstrologerProfile, AstrologerStatus, User
from app.main import create_app


@pytest.fixture
def test_clock() -> FrozenClock:
    """Deterministic frozen test clock."""
    return FrozenClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def test_settings() -> Settings:
    """Test configuration settings."""
    return Settings(
        ENVIRONMENT="test",
        JWT_SECRET="test-secret-key-that-is-at-least-32-chars-long",
        DATABASE_URL="sqlite:///:memory:",
        CORS_ALLOWED_ORIGINS=["http://localhost:3000"],
    )


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(
    db_session: Session, test_clock: FrozenClock, test_settings: Settings
) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with overridden dependencies."""
    app = create_app(settings=test_settings)

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def _override_get_clock() -> FrozenClock:
        return test_clock

    def _override_get_settings() -> Settings:
        return test_settings

    rate_limiter = InMemoryRateLimiter(clock=test_clock)

    def _override_get_rate_limiter() -> InMemoryRateLimiter:
        return rate_limiter

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_clock] = _override_get_clock
    app.dependency_overrides[get_settings] = _override_get_settings
    app.dependency_overrides[get_rate_limiter] = _override_get_rate_limiter

    with TestClient(app, base_url="http://localhost:3000") as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def user_factory(db_session: Session, test_clock: FrozenClock):
    """Factory creating users for tests."""

    def _create(
        email: str = "asha@example.com",
        password: str = "TestPassword2026!",
        role: UserRole = UserRole.USER,
        is_active: bool = True,
        astrologer_status: AstrologerStatus | None = None,
    ) -> User:
        now = test_clock.now()
        user = User(
            email=email.strip().lower(),
            password_hash=hash_password(password, for_testing=True),
            role=role,
            language="en",
            is_active=is_active,
            created_at=now,
            updated_at=now,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        if astrologer_status is not None:
            profile = AstrologerProfile(
                user_id=user.id,
                display_name="Jyotishi Shastri",
                credentials="10 years Vedic practice",
                tradition="Parashari",
                status=astrologer_status,
                approved_at=now if astrologer_status == AstrologerStatus.APPROVED else None,
            )
            db_session.add(profile)
            db_session.commit()

        return user

    return _create
