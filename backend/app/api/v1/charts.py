"""Chart generation and calculation endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.schemas.chart import (
    CalculationResponse,
    ChartCalculationRequest,
    ChartConflictErrorResponse,
    ChartSnapshotResponse,
    SnapshotResponse,
)
from app.api.schemas.dasha import DashaEligibilityError, DashaQuery, DashaResponse
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
from app.services.dasha_service import derive_snapshot_dasha
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
    response_model=CalculationResponse,
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
) -> CalculationResponse | Response:
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


@router.get(
    "/charts/{snapshot_id}/dasha",
    response_model=DashaResponse,
    responses={409: {"model": DashaEligibilityError}},
)
def read_chart_dasha(
    snapshot_id: uuid.UUID,
    query: Annotated[DashaQuery, Query()],
    current_user: User = Depends(require_permission(Permission.CHART_READ_OWN)),
    db: Session = Depends(get_db),
    app_settings: Settings = Depends(get_settings),
) -> DashaResponse | Response:
    """Derive a schedule from an owned snapshot without recalculating planetary positions."""
    try:
        snapshot = get_chart_snapshot(
            db,
            snapshot_id,
            owner_id=current_user.id,
            app_settings=app_settings,
        )
        db.rollback()
        if snapshot is None:
            return JSONResponse(status_code=404, content={"detail": "Item not found"})
        if not isinstance(snapshot, ChartSnapshotResponse):
            return JSONResponse(
                status_code=409,
                content=DashaEligibilityError(
                    code="DASHA_UNKNOWN_BIRTH_TIME",
                    detail="Vimshottari Dasha requires an exact or approximate birth time",
                ).model_dump(),
            )
        try:
            as_of = datetime.fromisoformat(query.as_of).astimezone(UTC) if query.as_of else None
        except (ValueError, OverflowError):
            return JSONResponse(status_code=422, content={"detail": "Invalid evaluation instant"})
        return derive_snapshot_dasha(snapshot, as_of)
    except Exception:
        db.rollback()
        logger.error("Chart Dasha derivation failed")
        return JSONResponse(status_code=500, content={"detail": "Unable to derive Dasha schedule"})


@router.get("/charts/{snapshot_id}", response_model=SnapshotResponse)
def read_chart_snapshot(
    snapshot_id: uuid.UUID,
    response: Response,
    current_user: User = Depends(require_permission(Permission.CHART_READ_OWN)),
    db: Session = Depends(get_db),
    app_settings: Settings = Depends(get_settings),
) -> SnapshotResponse | Response:
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
