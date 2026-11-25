"""Authenticated birth profile CRUD endpoints with 404 ownership isolation."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.schemas.profile import (
    BirthProfileCreate,
    BirthProfileListResponse,
    BirthProfileResponse,
    BirthProfileUpdate,
)
from app.core.clock import Clock
from app.core.config import Settings
from app.core.dependencies import (
    get_clock,
    get_current_user,
    get_db,
    get_owned_or_404,
    get_settings,
)
from app.core.permissions import Permission, require_permission
from app.db.models import BirthProfile, User
from app.services.profile_service import (
    ProfileStorageError,
    ProfileValidationError,
    create_profile,
    delete_profile,
    list_profiles,
    serialize_profile,
    update_profile,
)

router = APIRouter(
    prefix="/profiles",
    tags=["profiles"],
    dependencies=[Depends(require_permission(Permission.PROFILE_MANAGE_OWN))],
)


def _client_ip(request: Request) -> str | None:
    """Extract client IP safely without inspecting payloads."""
    return request.client.host if request.client else None


@router.post(
    "",
    response_model=BirthProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_birth_profile(
    req: BirthProfileCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> BirthProfileResponse:
    """Create a new encrypted birth profile belonging to the authenticated user."""
    try:
        return create_profile(
            db,
            owner_id=current_user.id,
            payload=req,
            clock=clock,
            settings=settings,
            ip=_client_ip(request),
        )
    except ProfileStorageError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to store birth profile securely",
        ) from None


@router.get("", response_model=BirthProfileListResponse)
def list_birth_profiles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BirthProfileListResponse:
    """List paginated birth profiles owned by the authenticated caller."""
    try:
        items, total = list_profiles(
            db,
            owner_id=current_user.id,
            settings=settings,
            limit=limit,
            offset=offset,
        )
    except ProfileStorageError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load birth profiles",
        ) from None
    return BirthProfileListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{profile_id}", response_model=BirthProfileResponse)
def get_birth_profile(
    profile_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BirthProfileResponse:
    """Retrieve a single owned birth profile (404 if missing or owned by another user)."""
    profile = get_owned_or_404(BirthProfile, profile_id, current_user.id, db)
    try:
        return serialize_profile(profile, owner_id=current_user.id, settings=settings)
    except ProfileStorageError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load birth profile",
        ) from None


@router.patch("/{profile_id}", response_model=BirthProfileResponse)
def patch_birth_profile(
    profile_id: uuid.UUID,
    req: BirthProfileUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> BirthProfileResponse | Response:
    """Partially update an owned birth profile after merged-state validation."""
    profile = get_owned_or_404(BirthProfile, profile_id, current_user.id, db)
    try:
        return update_profile(
            db,
            profile=profile,
            owner_id=current_user.id,
            payload=req,
            clock=clock,
            settings=settings,
            ip=_client_ip(request),
        )
    except ProfileValidationError as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": [
                    {
                        "type": "value_error",
                        "loc": ["body"],
                        "msg": str(exc),
                    }
                ]
            },
        )
    except ProfileStorageError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update birth profile",
        ) from None


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_birth_profile(
    profile_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Hard-delete an owned birth profile (404 if missing or owned by another user)."""
    profile = get_owned_or_404(BirthProfile, profile_id, current_user.id, db)
    delete_profile(db, profile=profile, owner_id=current_user.id, ip=_client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
