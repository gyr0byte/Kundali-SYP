"""Audit service for safely recording sensitive operations without leaking secrets or PII."""

import re
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog

# Substrings that must NEVER appear in audit metadata keys (top-level or nested)
FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "raw_token",
        "refresh_token",
        "secret",
        "credentials",
        "access_token",
        "reset_token",
        "birth_date",
        "birth_time",
        "birth_datetime",
        "entered_date",
        "date_ad",
        "time_local",
        "place_name",
        "birth_place",
        "latitude",
        "longitude",
        "timezone",
        "julian_day",
        "datetime_utc",
        "utc_offset",
        "time_utc",
        "lagna_longitude",
        "planet_positions",
        "chart_facts",
        "profile_label",
        "encryption_key",
        "ciphertext",
        "fernet",
        "_enc",
    }
)

# Exact token segments blocked in key names (split on non-alphanumeric separators)
FORBIDDEN_EXACT_TOKENS: frozenset[str] = frozenset(
    {"lat", "lon", "lng", "tz", "jd", "label", "email", "phone", "ssn"}
)

# Explicit structural allowlist for profile audit events (defense-in-depth over denylist)
ALLOWED_PROFILE_AUDIT_KEYS: frozenset[str] = frozenset(
    {
        "input_calendar",
        "time_certainty",
        "bs_conversion_status",
        "changed_fields",
    }
)

ALLOWED_PROFILE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "label",
        "input_calendar",
        "entered_date",
        "time_certainty",
        "time_local",
        "place_name",
        "latitude",
        "longitude",
        "timezone",
    }
)

ALLOWED_PROFILE_ACTIONS: frozenset[str] = frozenset(
    {
        "profile:create",
        "profile:update",
        "profile:delete",
    }
)

_ALLOWED_CALENDARS: frozenset[str] = frozenset({"AD", "BS"})
_ALLOWED_TIME_CERTAINTIES: frozenset[str] = frozenset({"exact", "approximate", "unknown"})
_ALLOWED_BS_STATUSES: frozenset[str] = frozenset({"resolved", "awaiting_bs_conversion"})

_DROP = object()


def _is_forbidden_key(key: str) -> bool:
    """Return True if a metadata key contains forbidden secret or PII identifiers."""
    lower_key = key.lower()
    if any(forbidden in lower_key for forbidden in FORBIDDEN_METADATA_KEYS):
        return True
    tokens = {tok for tok in re.split(r"[^a-z0-9]+", lower_key) if tok}
    return bool(tokens & FORBIDDEN_EXACT_TOKENS)


def _is_looks_like_secret_or_ciphertext(key: str, value: str) -> bool:
    """Reject Fernet tokens or oversized key/hash strings even under benign keys."""
    if len(value) >= 40 and value.startswith("gAAAAA"):
        return True
    lower_key = key.lower()
    return len(value) > 50 and any(h in lower_key for h in ("hash", "jwt", "key", "cipher"))


def _sanitize_value(key: str, value: Any) -> Any:
    """Recursively sanitize a metadata value, dropping binary/object/nested forbidden data."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if _is_looks_like_secret_or_ciphertext(key, value):
            return _DROP
        return value
    if isinstance(value, bytes | bytearray | memoryview):
        return _DROP
    if isinstance(value, Mapping):
        cleaned_nested = sanitize_metadata(value)
        if value and not cleaned_nested:
            return _DROP
        return cleaned_nested
    if isinstance(value, list | tuple):
        cleaned_items: list[Any] = []
        for item in value:
            sanitized_item = _sanitize_value(key, item)
            if sanitized_item is not _DROP:
                cleaned_items.append(sanitized_item)
        return cleaned_items
    # Drop ORM models, Pydantic objects, sets, dates, or arbitrary objects.
    return _DROP


def sanitize_metadata(meta: Mapping[str, Any] | None) -> dict[str, Any]:
    """Recursively sanitize metadata, stripping secrets, birth PII, bytes, and objects."""
    if not meta or not isinstance(meta, Mapping):
        return {}
    sanitized: dict[str, Any] = {}
    for raw_key, raw_value in meta.items():
        key = str(raw_key)
        if _is_forbidden_key(key):
            continue
        cleaned_val = _sanitize_value(key, raw_value)
        if cleaned_val is _DROP:
            continue
        sanitized[key] = cleaned_val
    return sanitized


def sanitize_profile_metadata(meta: Mapping[str, Any] | None) -> dict[str, Any]:
    """Strictly allowlist structural metadata permitted on birth-profile audit records."""
    if not meta or not isinstance(meta, Mapping):
        return {}

    cleaned: dict[str, Any] = {}

    raw_cal = meta.get("input_calendar")
    if isinstance(raw_cal, str) and str(raw_cal) in _ALLOWED_CALENDARS:
        cleaned["input_calendar"] = str(raw_cal)

    raw_certainty = meta.get("time_certainty")
    if isinstance(raw_certainty, str) and str(raw_certainty) in _ALLOWED_TIME_CERTAINTIES:
        cleaned["time_certainty"] = str(raw_certainty)

    raw_bs_status = meta.get("bs_conversion_status")
    if isinstance(raw_bs_status, str) and str(raw_bs_status) in _ALLOWED_BS_STATUSES:
        cleaned["bs_conversion_status"] = str(raw_bs_status)

    raw_changed = meta.get("changed_fields")
    if isinstance(raw_changed, list | tuple | set | frozenset):
        allowed_fields = sorted(
            {
                field
                for field in raw_changed
                if isinstance(field, str) and field in ALLOWED_PROFILE_FIELD_NAMES
            }
        )
        if allowed_fields:
            cleaned["changed_fields"] = allowed_fields

    return {k: v for k, v in cleaned.items() if k in ALLOWED_PROFILE_AUDIT_KEYS}


def log_action(
    db: Session,
    action: str,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditLog:
    """Safely create and persist an audit log entry."""
    if action.startswith("profile:") or target_type == "birth_profile":
        clean_meta = sanitize_metadata(sanitize_profile_metadata(metadata))
    else:
        clean_meta = sanitize_metadata(metadata)
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip=ip,
        event_metadata=clean_meta,
    )
    db.add(log)
    db.flush()
    return log


def log_profile_action(
    db: Session,
    *,
    action: str,
    actor_id: uuid.UUID,
    profile_id: uuid.UUID,
    ip: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditLog:
    """Record an allowlisted birth-profile audit event without logging PII or ciphertext."""
    if action not in ALLOWED_PROFILE_ACTIONS:
        raise ValueError("Unsupported birth-profile audit action")
    return log_action(
        db=db,
        action=action,
        actor_id=actor_id,
        target_type="birth_profile",
        target_id=str(profile_id),
        ip=ip,
        metadata=sanitize_profile_metadata(metadata),
    )
