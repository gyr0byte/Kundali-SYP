"""Authentication and user session endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.api.schemas.user import UserResponse
from app.core.clock import Clock
from app.core.config import Settings
from app.core.dependencies import (
    get_clock,
    get_current_user,
    get_db,
    get_mailer,
    get_rate_limiter,
    get_settings,
)
from app.core.mailer import Mailer
from app.core.rate_limit import InMemoryRateLimiter
from app.db.models import User
from app.services.auth_service import (
    authenticate_user,
    change_password,
    create_token_pair,
    refresh_tokens,
    register_user,
    request_password_reset,
    reset_password,
    revoke_all_tokens,
    revoke_token,
)

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    req: RegisterRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Register a new user account."""
    try:
        user = register_user(
            db=db,
            email=req.email,
            password=req.password,
            clock=clock,
            for_testing=(settings.ENVIRONMENT == "test"),
        )
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None


@router.post("/auth/login", response_model=TokenResponse)
def login(
    req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
    limiter: InMemoryRateLimiter = Depends(get_rate_limiter),
) -> Any:
    """Authenticate credentials and return an access and rotating refresh token."""
    # Apply sliding-window rate limit on login attempts
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"login:{client_ip}:{req.email.lower()}"
    allowed, retry_after = limiter.check_rate_limit(key=rate_key, limit=5, window_seconds=60)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        user = authenticate_user(
            db=db,
            email=req.email,
            password=req.password,
            clock=clock,
            for_testing=(settings.ENVIRONMENT == "test"),
        )
        access_token, refresh_token = create_token_pair(
            db=db, user=user, clock=clock, settings=settings
        )
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from None


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(
    req: RefreshRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Rotate an existing refresh token and issue a fresh access token."""
    try:
        new_access, new_refresh = refresh_tokens(
            db=db,
            raw_refresh_token=req.refresh_token,
            clock=clock,
            settings=settings,
        )
        return TokenResponse(access_token=new_access, refresh_token=new_refresh)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from None


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    req: LogoutRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    """Public single token revocation. Idempotent: returns 204 even if token is unknown."""
    revoke_token(db=db, raw_refresh_token=req.refresh_token, clock=clock)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    """Authenticated endpoint revoking all active sessions for the current user."""
    revoke_all_tokens(db=db, user_id=current_user.id, clock=clock)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> Any:
    """Return profile metadata for the authenticated user."""
    return current_user


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
def update_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Change current user's password and invalidate all active sessions."""
    try:
        change_password(
            db=db,
            user=current_user,
            old_password=req.old_password,
            new_password=req.new_password,
            clock=clock,
            for_testing=(settings.ENVIRONMENT == "test"),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None


@router.post("/auth/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    req: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    mailer: Mailer = Depends(get_mailer),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Request a password reset email. Always returns 202 to avoid leaking user existence."""
    request_password_reset(
        db=db,
        email=req.email,
        clock=clock,
        mailer=mailer,
        settings=settings,
    )
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_pwd(
    req: ResetPasswordRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Reset password using a single-use unexpired reset token."""
    try:
        reset_password(
            db=db,
            raw_reset_token=req.token,
            new_password=req.new_password,
            clock=clock,
            for_testing=(settings.ENVIRONMENT == "test"),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
