"""Core FastAPI dependencies for authentication, database, and system services."""

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.mailer import ConsoleMailer, Mailer
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import decode_access_token
from app.db.session import get_db

__all__ = [
    "get_clock",
    "get_current_user",
    "get_db",
    "get_mailer",
    "get_owned_or_404",
    "get_rate_limiter",
    "get_settings",
]

# Bearer token security scheme
oauth2_scheme = HTTPBearer(auto_error=False)

# Singleton instances
_system_clock = SystemClock()
_rate_limiter = InMemoryRateLimiter(clock=_system_clock)


def get_clock() -> Clock:
    """Dependency returning system clock."""
    return _system_clock


def get_mailer(settings: Settings = Depends(get_settings)) -> Mailer:
    """Dependency returning appropriate mailer for the environment."""
    return ConsoleMailer(environment=settings.ENVIRONMENT)


def get_rate_limiter() -> InMemoryRateLimiter:
    """Dependency returning application rate limiter."""
    return _rate_limiter


def get_current_user(
    auth: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Decode JWT access token and return the authenticated user."""
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(auth.credentials, secret=settings.JWT_SECRET)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    import uuid

    try:
        user_uuid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier in token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # Dynamic lookup from DB: import locally or use session.get
    from app.db.models.user import User

    user = db.get(User, user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_owned_or_404[T](
    model: type[T],
    item_id: Any,
    owner_id: Any,
    db: Session,
    owner_field: str = "owner_id",
) -> T:
    """Fetch an item by ID and verify ownership.

    Returns HTTP 404 for missing or non-owned resources.
    """
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    item_owner = getattr(item, owner_field, None)
    if str(item_owner) != str(owner_id):
        # Return 404 to avoid leaking existence of another user's resource
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    return item
