"""Audit service for safely recording sensitive operations without leaking secrets."""

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog

# Sensitive keys that must NEVER be written to audit logs
FORBIDDEN_METADATA_KEYS = {
    "password",
    "password_hash",
    "token",
    "raw_token",
    "refresh_token",
    "secret",
    "credentials",
    "access_token",
    "reset_token",
}


def sanitize_metadata(meta: Mapping[str, Any] | None) -> dict[str, Any]:
    """Sanitize metadata dictionary, removing any passwords or token values."""
    if not meta:
        return {}
    sanitized: dict[str, Any] = {}
    for k, v in meta.items():
        if any(forbidden in k.lower() for forbidden in FORBIDDEN_METADATA_KEYS):
            continue
        if (
            isinstance(v, str)
            and len(v) > 50
            and any(h in k.lower() for h in ("hash", "jwt", "key"))
        ):
            continue
        sanitized[k] = v
    return sanitized


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
