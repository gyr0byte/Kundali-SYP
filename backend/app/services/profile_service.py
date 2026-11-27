"""Service layer for encrypted birth profile CRUD operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas.profile import (
    BirthProfileCreate,
    BirthProfileResponse,
    BirthProfileUpdate,
    BsConversionStatus,
    validate_birth_profile_state,
)
from app.calc.bikram_sambat import CalendarDateError
from app.calc.timeconv import TimeConversionError
from app.core.clock import Clock
from app.core.config import Settings
from app.core.security import (
    DecryptionError,
    decrypt_float,
    decrypt_optional_text,
    decrypt_text,
    encrypt_float,
    encrypt_optional_text,
    encrypt_text,
)
from app.db.models.profile import BirthProfile, InputCalendar, TimeCertainty
from app.services.audit_service import log_profile_action


class ProfileValidationError(ValueError):
    """Raised when merged profile update data violates validation rules."""


class ProfileStorageError(RuntimeError):
    """Raised when encrypted birth profile fields cannot be protected or decoded."""


@dataclass(frozen=True)
class ProfileCalcInputs:
    """In-memory decrypted birth fields needed strictly for deterministic calculation."""

    profile_id: uuid.UUID
    updated_at: datetime
    input_calendar: InputCalendar
    time_certainty: TimeCertainty
    date_ad: str | None
    time_local: str | None
    latitude: float
    longitude: float
    timezone: str


def decrypt_profile_calc_inputs(
    profile: BirthProfile,
    *,
    owner_id: uuid.UUID,
    settings: Settings,
) -> ProfileCalcInputs:
    """Decrypt strictly calculation-required profile fields for the verified owner.

    Intentionally skips non-calculation identity fields (``label_enc``,
    ``entered_date_enc``, ``place_name_enc``) to minimize plaintext exposure in memory.
    """
    if str(profile.owner_id) != str(owner_id):
        raise PermissionError("Profile ownership mismatch")

    key = settings.ENCRYPTION_KEY
    try:
        date_ad = decrypt_optional_text(profile.date_ad_enc, key)
        time_local = decrypt_optional_text(profile.time_local_enc, key)
        latitude = decrypt_float(profile.latitude_enc, key)
        longitude = decrypt_float(profile.longitude_enc, key)
        timezone_name = decrypt_text(profile.timezone_enc, key)
    except (DecryptionError, ValueError):
        raise ProfileStorageError("Unable to decrypt stored birth profile") from None

    return ProfileCalcInputs(
        profile_id=profile.id,
        updated_at=profile.updated_at,
        input_calendar=profile.input_calendar,
        time_certainty=profile.time_certainty,
        date_ad=date_ad,
        time_local=time_local,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone_name,
    )


def _compute_bs_status(input_calendar: InputCalendar, date_ad: str | None) -> BsConversionStatus:
    """Compute explicit BS conversion status without fabricating dates."""
    if input_calendar == InputCalendar.BS and date_ad is None:
        return "awaiting_bs_conversion"
    return "resolved"


def serialize_profile(
    profile: BirthProfile,
    *,
    owner_id: uuid.UUID,
    settings: Settings,
) -> BirthProfileResponse:
    """Decrypt and serialize a BirthProfile exclusively for its authenticated owner."""
    if str(profile.owner_id) != str(owner_id):
        raise PermissionError("Profile ownership mismatch")

    key = settings.ENCRYPTION_KEY
    try:
        label = decrypt_text(profile.label_enc, key)
        entered_date = decrypt_text(profile.entered_date_enc, key)
        date_ad = decrypt_optional_text(profile.date_ad_enc, key)
        time_local = decrypt_optional_text(profile.time_local_enc, key)
        place_name = decrypt_text(profile.place_name_enc, key)
        latitude = decrypt_float(profile.latitude_enc, key)
        longitude = decrypt_float(profile.longitude_enc, key)
        timezone_name = decrypt_text(profile.timezone_enc, key)
    except (DecryptionError, ValueError):
        raise ProfileStorageError("Unable to decrypt stored birth profile") from None

    return BirthProfileResponse(
        id=profile.id,
        owner_id=profile.owner_id,
        label=label,
        input_calendar=profile.input_calendar,
        entered_date=entered_date,
        date_ad=date_ad,
        bs_conversion_status=_compute_bs_status(profile.input_calendar, date_ad),
        time_certainty=profile.time_certainty,
        time_local=time_local,
        place_name=place_name,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone_name,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def create_profile(
    db: Session,
    *,
    owner_id: uuid.UUID,
    payload: BirthProfileCreate,
    clock: Clock,
    settings: Settings,
    ip: str | None = None,
) -> BirthProfileResponse:
    """Encrypt and persist a new birth profile owned by the caller."""
    validated = payload.validated()

    now = clock.now()
    key = settings.ENCRYPTION_KEY
    try:
        profile = BirthProfile(
            owner_id=owner_id,
            label_enc=encrypt_text(validated.label, key),
            input_calendar=validated.input_calendar,
            entered_date_enc=encrypt_text(validated.entered_date, key),
            date_ad_enc=encrypt_optional_text(validated.date_ad, key),
            time_certainty=validated.time_certainty,
            time_local_enc=encrypt_optional_text(validated.time_local, key),
            place_name_enc=encrypt_text(validated.place_name, key),
            latitude_enc=encrypt_float(validated.latitude, key),
            longitude_enc=encrypt_float(validated.longitude, key),
            timezone_enc=encrypt_text(validated.timezone, key),
            created_at=now,
            updated_at=now,
        )
    except ValueError:
        raise ProfileStorageError("Unable to protect birth profile data") from None

    db.add(profile)
    db.flush()

    log_profile_action(
        db,
        action="profile:create",
        actor_id=owner_id,
        profile_id=profile.id,
        ip=ip,
        metadata={
            "input_calendar": validated.input_calendar.value,
            "time_certainty": validated.time_certainty.value,
            "bs_conversion_status": validated.bs_conversion_status,
        },
    )
    db.commit()
    db.refresh(profile)
    return serialize_profile(profile, owner_id=owner_id, settings=settings)


def list_profiles(
    db: Session,
    *,
    owner_id: uuid.UUID,
    settings: Settings,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[BirthProfileResponse], int]:
    """List paginated birth profiles belonging strictly to the authenticated owner."""
    total = (
        db.scalar(select(func.count(BirthProfile.id)).where(BirthProfile.owner_id == owner_id)) or 0
    )
    rows = db.scalars(
        select(BirthProfile)
        .where(BirthProfile.owner_id == owner_id)
        .order_by(BirthProfile.created_at.desc(), BirthProfile.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [serialize_profile(row, owner_id=owner_id, settings=settings) for row in rows]
    return items, total


def update_profile(
    db: Session,
    *,
    profile: BirthProfile,
    owner_id: uuid.UUID,
    payload: BirthProfileUpdate,
    clock: Clock,
    settings: Settings,
    ip: str | None = None,
) -> BirthProfileResponse:
    """Validate and apply partial updates against merged existing profile state."""
    current = serialize_profile(profile, owner_id=owner_id, settings=settings)
    fields_set = payload.model_fields_set

    merged_label = (
        payload.label if "label" in fields_set and payload.label is not None else current.label
    )
    merged_calendar = (
        payload.input_calendar
        if "input_calendar" in fields_set and payload.input_calendar is not None
        else current.input_calendar
    )
    merged_entered_date = (
        payload.entered_date
        if "entered_date" in fields_set and payload.entered_date is not None
        else current.entered_date
    )
    merged_certainty = (
        payload.time_certainty
        if "time_certainty" in fields_set and payload.time_certainty is not None
        else current.time_certainty
    )

    if merged_certainty == TimeCertainty.UNKNOWN:
        if "time_local" in fields_set and payload.time_local is not None:
            raise ProfileValidationError(
                "Local birth time must be omitted when time certainty is unknown"
            )
        merged_time_local: str | None = None
    elif "time_local" in fields_set:
        merged_time_local = payload.time_local
    else:
        merged_time_local = current.time_local

    merged_place = (
        payload.place_name
        if "place_name" in fields_set and payload.place_name is not None
        else current.place_name
    )
    merged_lat = (
        payload.latitude
        if "latitude" in fields_set and payload.latitude is not None
        else current.latitude
    )
    merged_lon = (
        payload.longitude
        if "longitude" in fields_set and payload.longitude is not None
        else current.longitude
    )
    merged_tz = (
        payload.timezone
        if "timezone" in fields_set and payload.timezone is not None
        else current.timezone
    )

    try:
        validated = validate_birth_profile_state(
            label=merged_label,
            input_calendar=merged_calendar,
            entered_date=merged_entered_date,
            time_certainty=merged_certainty,
            time_local=merged_time_local,
            place_name=merged_place,
            latitude=merged_lat,
            longitude=merged_lon,
            timezone=merged_tz,
        )
    except (CalendarDateError, TimeConversionError):
        raise
    except ValueError as exc:
        raise ProfileValidationError(str(exc)) from None

    changed_fields: list[str] = []
    comparisons = [
        ("label", current.label, validated.label),
        ("input_calendar", current.input_calendar, validated.input_calendar),
        ("entered_date", current.entered_date, validated.entered_date),
        ("time_certainty", current.time_certainty, validated.time_certainty),
        ("time_local", current.time_local, validated.time_local),
        ("place_name", current.place_name, validated.place_name),
        ("latitude", current.latitude, validated.latitude),
        ("longitude", current.longitude, validated.longitude),
        ("timezone", current.timezone, validated.timezone),
    ]
    for field_name, old_val, new_val in comparisons:
        if old_val != new_val:
            changed_fields.append(field_name)

    key = settings.ENCRYPTION_KEY
    try:
        profile.label_enc = encrypt_text(validated.label, key)
        profile.input_calendar = validated.input_calendar
        profile.entered_date_enc = encrypt_text(validated.entered_date, key)
        profile.date_ad_enc = encrypt_optional_text(validated.date_ad, key)
        profile.time_certainty = validated.time_certainty
        profile.time_local_enc = encrypt_optional_text(validated.time_local, key)
        profile.place_name_enc = encrypt_text(validated.place_name, key)
        profile.latitude_enc = encrypt_float(validated.latitude, key)
        profile.longitude_enc = encrypt_float(validated.longitude, key)
        profile.timezone_enc = encrypt_text(validated.timezone, key)
    except ValueError:
        raise ProfileStorageError("Unable to protect birth profile data") from None

    profile.revision += 1
    profile.updated_at = clock.now()
    db.flush()

    log_profile_action(
        db,
        action="profile:update",
        actor_id=owner_id,
        profile_id=profile.id,
        ip=ip,
        metadata={
            "input_calendar": validated.input_calendar.value,
            "time_certainty": validated.time_certainty.value,
            "bs_conversion_status": validated.bs_conversion_status,
            "changed_fields": changed_fields,
        },
    )
    db.commit()
    db.refresh(profile)
    return serialize_profile(profile, owner_id=owner_id, settings=settings)


def delete_profile(
    db: Session,
    *,
    profile: BirthProfile,
    owner_id: uuid.UUID,
    ip: str | None = None,
) -> None:
    """Hard-delete an owned birth profile and emit an allowlisted audit entry."""
    if str(profile.owner_id) != str(owner_id):
        raise PermissionError("Profile ownership mismatch")

    profile_id = profile.id
    input_calendar_val = profile.input_calendar.value
    certainty_val = profile.time_certainty.value

    db.delete(profile)
    log_profile_action(
        db,
        action="profile:delete",
        actor_id=owner_id,
        profile_id=profile_id,
        ip=ip,
        metadata={
            "input_calendar": input_calendar_val,
            "time_certainty": certainty_val,
        },
    )
    db.commit()
