"""Service layer orchestrating deterministic chart computation for owned birth profiles."""

from __future__ import annotations

import datetime
import hmac
import json
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from app.api.schemas.chart import (
    ChartCalculationResponse,
    ChartConflictErrorCode,
    ChartFactUnits,
    ChartSnapshotResponse,
)
from app.calc.ayanamsha import CalculationError
from app.calc.ephemeris import EphemerisDateRangeError
from app.calc.facts import ChartSettings, compute_chart_facts
from app.calc.timeconv import TimeConversionError, TimeInput
from app.core.config import Settings
from app.core.security import decrypt_text, encrypt_text
from app.db.models.chart import ChartSnapshot
from app.db.models.profile import BirthProfile, InputCalendar, TimeCertainty
from app.services.profile_service import ProfileCalcInputs, decrypt_profile_calc_inputs

SNAPSHOT_SCHEMA_VERSION = 1


class _StoredSnapshotV1(BaseModel):
    """Versioned encrypted document, with immutable engine-order facts and their units."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    snapshot_id: uuid.UUID
    profile_revision: int
    fact_units: ChartFactUnits
    result: ChartCalculationResponse


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
        "dst_gap": "A clock change skipped this local birth time in the profile timezone.",
        "dst_overlap": "A clock change repeated this local birth time in the profile timezone.",
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
    if profile.input_calendar == InputCalendar.BS and profile.date_ad_enc is None:
        raise ChartProfileConflictError(
            code="AWAITING_BS_CONVERSION",
            detail=("Review and save the birth date to resolve this legacy Bikram Sambat profile."),
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
    if calc_inputs.input_calendar == InputCalendar.BS and calc_inputs.date_ad is None:
        raise ChartProfileConflictError(
            code="AWAITING_BS_CONVERSION",
            detail=("Review and save the birth date to resolve this legacy Bikram Sambat profile."),
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


def _fingerprint_key(profile_id: uuid.UUID, chart_id: str, encryption_key: str) -> str:
    """Index the existing fingerprint without publishing equality across profiles."""
    message = f"kundali:chart-snapshot:lookup:v1:{profile_id}:{chart_id}".encode()
    return hmac.digest(encryption_key.encode("ascii"), message, "sha256").hex()


def persist_chart_snapshot(
    db: Session,
    result: ChartCalculationResponse,
    *,
    profile_revision: int,
    owner_id: uuid.UUID,
    app_settings: Settings,
) -> uuid.UUID:
    """Lock the parent briefly to verify freshness and serialize same-profile inserts."""
    live_revision = db.scalar(
        select(BirthProfile.revision)
        .where(BirthProfile.id == result.profile_id, BirthProfile.owner_id == owner_id)
        .with_for_update(key_share=True)
    )
    if live_revision != profile_revision:
        raise ChartProfileConflictError(
            code="PROFILE_CHANGED",
            detail=(
                "The birth profile changed or was removed during calculation. "
                "Reopen the profile and retry."
            ),
        )

    key = app_settings.ENCRYPTION_KEY
    fingerprint = _fingerprint_key(result.profile_id, result.chart.chart_id, key)
    snapshot_id = db.scalar(
        select(ChartSnapshot.id).where(
            ChartSnapshot.profile_id == result.profile_id,
            ChartSnapshot.profile_revision == profile_revision,
            ChartSnapshot.schema_version == SNAPSHOT_SCHEMA_VERSION,
            ChartSnapshot.fingerprint_key == fingerprint,
        )
    )
    if snapshot_id is None:
        snapshot_id = uuid.uuid4()
        document = _StoredSnapshotV1(
            snapshot_id=snapshot_id,
            profile_revision=profile_revision,
            result=result,
            fact_units=ChartFactUnits(),
        )
        canonical = json.dumps(
            document.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        db.add(
            ChartSnapshot(
                id=snapshot_id,
                profile_id=result.profile_id,
                profile_revision=profile_revision,
                schema_version=SNAPSHOT_SCHEMA_VERSION,
                fingerprint_key=fingerprint,
                payload_enc=encrypt_text(canonical, key),
            )
        )
    db.commit()
    return snapshot_id


def get_chart_snapshot(
    db: Session, snapshot_id: uuid.UUID, *, owner_id: uuid.UUID, app_settings: Settings
) -> ChartSnapshotResponse | None:
    """Read and decrypt a snapshot after checking live profile ownership."""
    row = db.execute(
        select(ChartSnapshot, BirthProfile.revision)
        .join(BirthProfile, ChartSnapshot.profile_id == BirthProfile.id)
        .where(ChartSnapshot.id == snapshot_id, BirthProfile.owner_id == owner_id)
        .options(undefer(ChartSnapshot.payload_enc))
    ).one_or_none()
    if row is None:
        return None

    snapshot, current_revision = row
    if snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Unsupported chart snapshot schema")
    key = app_settings.ENCRYPTION_KEY
    stored = _StoredSnapshotV1.model_validate_json(decrypt_text(snapshot.payload_enc, key))
    if (
        stored.snapshot_id != snapshot.id
        or stored.profile_revision != snapshot.profile_revision
        or stored.result.profile_id != snapshot.profile_id
        or not hmac.compare_digest(
            snapshot.fingerprint_key,
            _fingerprint_key(snapshot.profile_id, stored.result.chart.chart_id, key),
        )
    ):
        raise ValueError("Chart snapshot integrity check failed")

    return ChartSnapshotResponse(
        **stored.result.model_dump(),
        snapshot_id=snapshot.id,
        schema_version=stored.schema_version,
        profile_revision=stored.profile_revision,
        is_current_profile_revision=current_revision == stored.profile_revision,
        created_at=(
            snapshot.created_at
            if snapshot.created_at.tzinfo is not None
            else snapshot.created_at.replace(tzinfo=datetime.UTC)
        ),
        fact_units=stored.fact_units,
    )
