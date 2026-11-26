"""Chart generation and calculation endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.schemas.chart import (
    ChartCalculationRequest,
    ChartCalculationResponse,
    ChartConflictErrorResponse,
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
)
from app.services.profile_service import ProfileStorageError

router = APIRouter(tags=["charts"])

_NO_STORE_HEADERS = {"Cache-Control": "no-store"}


@router.post(
    "/profiles/{profile_id}/chart",
    response_model=ChartCalculationResponse,
    status_code=status.HTTP_200_OK,
    responses={
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
    profile = get_owned_or_404(BirthProfile, profile_id, current_user.id, db)
    calc_settings = req.to_chart_settings()

    try:
        result = calculate_profile_chart(
            profile,
            owner_id=current_user.id,
            calc_settings=calc_settings,
            app_settings=app_settings,
        )
    except ChartProfileConflictError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.detail, "code": exc.code},
            headers=_NO_STORE_HEADERS,
        )
    except ChartTimeInputError as exc:
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
    except (ProfileStorageError, ChartCalculationFailureError, Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Unable to compute birth chart"},
            headers=_NO_STORE_HEADERS,
        )

    response.headers["Cache-Control"] = "no-store"
    return result
