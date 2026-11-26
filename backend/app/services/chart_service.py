"""Service layer orchestrating deterministic chart computation for owned birth profiles."""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import ValidationError

from app.api.schemas.chart import ChartCalculationResponse, ChartConflictErrorCode
from app.calc.ayanamsha import CalculationError
from app.calc.ephemeris import EphemerisDateRangeError
from app.calc.facts import ChartSettings, compute_chart_facts
from app.calc.timeconv import TimeConversionError, TimeInput
from app.core.config import Settings
from app.db.models.profile import BirthProfile, InputCalendar, TimeCertainty
from app.services.profile_service import ProfileCalcInputs, decrypt_profile_calc_inputs


class ChartProfileConflictError(RuntimeError):
    """Raised when a profile state precludes deterministic calculation (HTTP 409)."""

    def __init__(self, *, code: ChartConflictErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class ChartTimeInputError(ValueError):
    """Raised when known birth time or timezone transition validation fails (HTTP 422)."""

    def __init__(self, *, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class ChartCalculationFailureError(RuntimeError):
    """An internal failure with a fixed, privacy-safe diagnostic category (HTTP 500)."""

    def __init__(
        self,
        *,
        category: Literal["invalid_stored_birth_data", "native_calculation", "unexpected"],
    ) -> None:
        super().__init__("Unable to compute birth chart")
        self.category = category


def _map_time_conversion_error(exc: TimeConversionError) -> ChartTimeInputError:
    """Translate TimeConversionError into a sanitized PII-free domain error."""
    messages_by_code = {
        "dst_gap": "Birth time falls within a daylight saving time gap for the profile timezone.",
        "dst_overlap": (
            "Birth time falls within an ambiguous daylight saving time overlap "
            "for the profile timezone."
        ),
        "invalid_timezone": "Birth profile timezone is invalid or unsupported.",
        "invalid_coordinates": "Birth profile coordinates are out of valid geographic bounds.",
        "invalid_utc_offset": "Birth profile UTC offset is invalid.",
        "missing_timezone_spec": "Birth profile timezone specification is missing.",
        "conflicting_timezone_spec": "Birth profile timezone specification is conflicting.",
    }
    safe_msg = messages_by_code.get(
        exc.code,
        "Birth date, time, or timezone cannot be resolved for calculation.",
    )
    return ChartTimeInputError(code=exc.code, detail=safe_msg)


def _validate_supported_profile_state(profile: BirthProfile) -> None:
    """Enforce unsupported-state checks before decrypting or invoking Swiss Ephemeris."""
    if profile.input_calendar == InputCalendar.BS:
        raise ChartProfileConflictError(
            code="AWAITING_BS_CONVERSION",
            detail=(
                "Chart calculation is unavailable until Bikram Sambat date conversion is supported."
            ),
        )
    if profile.time_certainty == TimeCertainty.UNKNOWN:
        raise ChartProfileConflictError(
            code="UNKNOWN_TIME_UNSUPPORTED",
            detail=(
                "Chart calculation requires a recorded birth time; unknown birth time "
                "is unsupported."
            ),
        )


def _ensure_complete_decrypted_inputs(calc_inputs: ProfileCalcInputs) -> tuple[str, str, str]:
    """Verify decrypted calculation fields are complete before constructing TimeInput."""
    if calc_inputs.input_calendar == InputCalendar.BS:
        raise ChartProfileConflictError(
            code="AWAITING_BS_CONVERSION",
            detail=(
                "Chart calculation is unavailable until Bikram Sambat date conversion is supported."
            ),
        )
    if not calc_inputs.date_ad or not calc_inputs.date_ad.strip():
        raise ChartProfileConflictError(
            code="INCOMPLETE_BIRTH_DATA",
            detail="Birth profile is missing resolved Gregorian AD date information.",
        )
    if calc_inputs.time_certainty == TimeCertainty.UNKNOWN:
        raise ChartProfileConflictError(
            code="UNKNOWN_TIME_UNSUPPORTED",
            detail=(
                "Chart calculation requires a recorded birth time; unknown birth time "
                "is unsupported."
            ),
        )
    if not calc_inputs.time_local or not calc_inputs.time_local.strip():
        raise ChartProfileConflictError(
            code="INCOMPLETE_BIRTH_DATA",
            detail="Birth profile is missing local birth time information.",
        )
    if not calc_inputs.timezone or not calc_inputs.timezone.strip():
        raise ChartProfileConflictError(
            code="INCOMPLETE_BIRTH_DATA",
            detail="Birth profile is missing timezone information.",
        )
    return (
        calc_inputs.date_ad.strip(),
        calc_inputs.time_local.strip(),
        calc_inputs.timezone.strip(),
    )


def calculate_profile_chart(
    profile: BirthProfile,
    *,
    owner_id: uuid.UUID,
    calc_settings: ChartSettings,
    app_settings: Settings,
) -> ChartCalculationResponse:
    """Decrypt owned birth profile fields in memory and compute deterministic ChartFacts.

    Does not persist charts, cache computed outputs, or emit per-request AuditLog records.
    """
    if str(profile.owner_id) != str(owner_id):
        raise PermissionError("Profile ownership mismatch")

    _validate_supported_profile_state(profile)

    calc_inputs = decrypt_profile_calc_inputs(
        profile,
        owner_id=owner_id,
        settings=app_settings,
    )
    date_ad_str, time_local_str, timezone_str = _ensure_complete_decrypted_inputs(calc_inputs)

    try:
        parsed_date = datetime.date.fromisoformat(date_ad_str)
        parsed_time = datetime.time.fromisoformat(time_local_str)
    except ValueError:
        raise ChartCalculationFailureError(category="invalid_stored_birth_data") from None

    try:
        birth_input = TimeInput(
            date=parsed_date,
            time=parsed_time,
            latitude=calc_inputs.latitude,
            longitude=calc_inputs.longitude,
            timezone=timezone_str,
        )
    except TimeConversionError as exc:
        raise _map_time_conversion_error(exc) from None
    except ValidationError:
        raise ChartTimeInputError(
            code="invalid_time_input",
            detail="Birth date, time, or coordinate parameters failed validation.",
        ) from None

    try:
        chart = compute_chart_facts(birth_input=birth_input, settings=calc_settings)
    except TimeConversionError as exc:
        raise _map_time_conversion_error(exc) from None
    except EphemerisDateRangeError:
        raise ChartProfileConflictError(
            code="CHART_DATE_OUT_OF_RANGE",
            detail=(
                "The birth date is outside the available ephemeris coverage. "
                "Check the saved birth date or contact support."
            ),
        ) from None
    except CalculationError:
        raise ChartCalculationFailureError(category="native_calculation") from None
    except Exception:
        raise ChartCalculationFailureError(category="unexpected") from None

    return ChartCalculationResponse(
        profile_id=calc_inputs.profile_id,
        profile_updated_at=calc_inputs.updated_at,
        input_calendar=calc_inputs.input_calendar,
        time_certainty=calc_inputs.time_certainty,
        chart=chart,
    )
