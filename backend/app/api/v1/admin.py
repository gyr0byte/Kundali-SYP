"""Administrative panel endpoints."""

from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas.audit import AuditLogListResponse, AuditLogResponse
from app.api.schemas.user import (
    AstrologerListResponse,
    AstrologerProfileResponse,
    UserListResponse,
    UserResponse,
)
from app.core.clock import Clock
from app.core.dependencies import get_clock, get_current_user, get_db
from app.core.permissions import UserRole, require_role
from app.db.models import AstrologerProfile, AstrologerStatus, AuditLog, User
from app.services.astrologer_service import (
    approve_astrologer,
    list_astrologers,
    suspend_astrologer,
)
from app.services.user_service import deactivate_user, list_users, reactivate_user

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


@router.get("/users", response_model=UserListResponse)
def get_users(
    role: UserRole | None = None,
    is_active: bool | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Any:
    """List users filtered by role or status with pagination."""
    items, total = list_users(db, role=role, is_active=is_active, limit=limit, offset=offset)
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/users/{user_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
def deactivate(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    """Deactivate a user account and invalidate active sessions."""
    try:
        deactivate_user(
            db=db,
            target_user_id=user_id,
            actor_user_id=current_user.id,
            clock=clock,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.post("/users/{user_id}/reactivate", status_code=status.HTTP_204_NO_CONTENT)
def reactivate(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Reactivate a user account."""
    try:
        reactivate_user(
            db=db,
            target_user_id=user_id,
            actor_user_id=current_user.id,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.get("/astrologers", response_model=AstrologerListResponse)
def get_astrologers(
    status_filter: AstrologerStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Any:
    """List astrologer profiles with optional status filter."""
    items, total = list_astrologers(db, status=status_filter, limit=limit, offset=offset)
    return AstrologerListResponse(
        items=[AstrologerProfileResponse.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/astrologers/{user_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
def approve(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    """Approve astrologer application and upgrade account role."""
    try:
        approve_astrologer(
            db=db,
            user_id=user_id,
            admin_id=current_user.id,
            clock=clock,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.post("/astrologers/{user_id}/suspend", status_code=status.HTTP_204_NO_CONTENT)
def suspend(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    """Suspend astrologer credentials and invalidate active sessions."""
    try:
        suspend_astrologer(
            db=db,
            user_id=user_id,
            admin_id=current_user.id,
            clock=clock,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.get("/audit", response_model=AuditLogListResponse)
def get_audit_logs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Any:
    """List paginated audit log entries."""
    count_query = select(func.count(AuditLog.id))
    total = db.scalar(count_query) or 0

    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    logs = db.scalars(query).all()

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        limit=limit,
        offset=offset,
    )
