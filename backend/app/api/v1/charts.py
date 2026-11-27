"""Chart generation and calculation endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Body, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.schemas.chart import (
    ChartCalculationRequest,
    ChartCalculationResponse,
    ChartConflictErrorResponse,
    ChartSnapshotResponse,
)
from app.core.config import Settings
from app.core.dependencies import get_db, get_owned_or_404, get_settings
from app.core.permissions import Permission, require_permission
from app.db.models import BirthProfile, User
from app.services.chart_service import (
    ChartCalculationFailureError,
    ChartProfileConflictError,
    ChartTimeInputError,
    calculate_profile_chart,
    get_chart_snapshot,
    persist_chart_snapshot,
)
from app.services.profile_service import ProfileStorageError

router = APIRouter(tags=["charts"])
logger = logging.getLogger(__name__)

_NO_STORE_HEADERS = {"Cache-Control": "no-store"}


def _internal_failure(category: str) -> JSONResponse:
    logger.error("Chart calculation failed: %s", category)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Unable to compute birth chart"},
        headers=_NO_STORE_HEADERS,
    )


@router.post(
    "/profiles/{profile_id}/chart",
    response_model=ChartCalculationResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "headers": {
                "Location": {"description": "Saved snapshot URL", "schema": {"type": "string"}}
            }
        },
        status.HTTP_409_CONFLICT: {"model": ChartConflictErrorResponse},
    },
)
def compute_profile_chart_endpoint(
    profile_id: uuid.UUID,
    response: Response,
    req: ChartCalculationRequest = Body(default_factory=ChartCalculationRequest),
    current_user: User = Depends(require_permission(Permission.CHART_READ_OWN)),
    db: Session = Depends(get_db),
    app_settings: Settings = Depends(get_settings),
) -> ChartCalculationResponse | Response:
    """Compute a deterministic Vedic chart for an owned, calculation-eligible birth profile."""
    owner_id = current_user.id
    profile = get_owned_or_404(BirthProfile, profile_id, owner_id, db)

    try:
        profile_revision = profile.revision
        # Detach the loaded columns and release the read transaction during native computation.
        db.expunge(profile)
        db.rollback()
        result = calculate_profile_chart(
            profile,
            owner_id=owner_id,
            calc_settings=req.to_chart_settings(),
            app_settings=app_settings,
        )
        snapshot_id = persist_chart_snapshot(
            db,
            result,
            profile_revision=profile_revision,
            owner_id=owner_id,
            app_settings=app_settings,
        )
    except ChartProfileConflictError as exc:
        db.rollback()
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.detail, "code": exc.code},
            headers=_NO_STORE_HEADERS,
        )
    except ChartTimeInputError as exc:
        logger.warning("Chart calculation failed: time_conversion")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": [
                    {
                        "type": "value_error",
                        "loc": ["profile"],
                        "msg": exc.detail,
                    }
                ],
                "code": exc.code,
            },
            headers=_NO_STORE_HEADERS,
        )
    except ProfileStorageError:
        db.rollback()
        return _internal_failure("profile_decryption")
    except ChartCalculationFailureError as exc:
        return _internal_failure(exc.category)
    except Exception:
        db.rollback()
        return _internal_failure("unexpected")

    response.headers["Cache-Control"] = "no-store"
    response.headers["Location"] = f"/api/v1/charts/{snapshot_id}"
    return result


@router.get("/charts/{snapshot_id}", response_model=ChartSnapshotResponse)
def read_chart_snapshot(
    snapshot_id: uuid.UUID,
    response: Response,
    current_user: User = Depends(require_permission(Permission.CHART_READ_OWN)),
    db: Session = Depends(get_db),
    app_settings: Settings = Depends(get_settings),
) -> ChartSnapshotResponse | Response:
    """Retrieve an owned immutable result by its opaque resource ID."""
    try:
        result = get_chart_snapshot(
            db, snapshot_id, owner_id=current_user.id, app_settings=app_settings
        )
    except Exception:
        db.rollback()
        logger.error("Chart snapshot read failed")
        return JSONResponse(
            status_code=500,
            content={"detail": "Unable to read chart snapshot"},
            headers=_NO_STORE_HEADERS,
        )
    if result is None:
        return JSONResponse(
            status_code=404, content={"detail": "Item not found"}, headers=_NO_STORE_HEADERS
        )
    response.headers["Cache-Control"] = "no-store"
    return result
