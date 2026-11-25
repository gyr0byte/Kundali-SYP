"""Unit tests for BirthProfile ORM model, cascades, Alembic offline SQL, and audit privacy."""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import encrypt_float, encrypt_optional_text, encrypt_text
from app.db.base import Base
from app.db.models import (
    AuditLog,
    BirthProfile,
    InputCalendar,
    TimeCertainty,
    User,
)
from app.services.audit_service import (
    log_action,
    log_profile_action,
    sanitize_metadata,
    sanitize_profile_metadata,
)
from tests.conftest import TEST_ENCRYPTION_KEY

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _make_encrypted_profile(
    *,
    owner_id: uuid.UUID,
    label: str = "Asha Birth",
    input_calendar: InputCalendar = InputCalendar.AD,
    entered_date: str = "1998-07-31",
    date_ad: str | None = "1998-07-31",
    time_certainty: TimeCertainty = TimeCertainty.EXACT,
    time_local: str | None = "08:30",
    place_name: str = "Kathmandu, Nepal",
    latitude: float = 27.7172,
    longitude: float = 85.3240,
    timezone_name: str = "Asia/Kathmandu",
) -> BirthProfile:
    """Create a BirthProfile ORM instance with encrypted identity/location fields."""
    return BirthProfile(
        owner_id=owner_id,
        label_enc=encrypt_text(label, TEST_ENCRYPTION_KEY),
        input_calendar=input_calendar,
        entered_date_enc=encrypt_text(entered_date, TEST_ENCRYPTION_KEY),
        date_ad_enc=encrypt_optional_text(date_ad, TEST_ENCRYPTION_KEY),
        time_certainty=time_certainty,
        time_local_enc=encrypt_optional_text(time_local, TEST_ENCRYPTION_KEY),
        place_name_enc=encrypt_text(place_name, TEST_ENCRYPTION_KEY),
        latitude_enc=encrypt_float(latitude, TEST_ENCRYPTION_KEY),
        longitude_enc=encrypt_float(longitude, TEST_ENCRYPTION_KEY),
        timezone_enc=encrypt_text(timezone_name, TEST_ENCRYPTION_KEY),
    )


def test_birth_profile_encrypted_columns_and_schema_shape(db_session: Session) -> None:
    """Sensitive birth fields are stored encrypted while only structural columns remain plain."""
    user = User(email="encrypted_owner@example.com", password_hash="hash")
    db_session.add(user)
    db_session.commit()

    profile = _make_encrypted_profile(
        owner_id=user.id,
        label="आशा जन्म",
        place_name="काठमाडौं, नेपाल",
    )
    db_session.add(profile)
    db_session.commit()

    expected_columns = {
        "id",
        "owner_id",
        "label_enc",
        "input_calendar",
        "entered_date_enc",
        "date_ad_enc",
        "time_certainty",
        "time_local_enc",
        "place_name_enc",
        "latitude_enc",
        "longitude_enc",
        "timezone_enc",
        "created_at",
        "updated_at",
    }
    assert set(BirthProfile.__table__.columns.keys()) == expected_columns
    index_names = {idx.name for idx in BirthProfile.__table__.indexes}
    assert "ix_birth_profiles_owner_id" in index_names

    raw_row = db_session.execute(
        text(
            "SELECT label_enc, entered_date_enc, date_ad_enc, time_local_enc, "
            "place_name_enc, latitude_enc, longitude_enc, timezone_enc, "
            "input_calendar, time_certainty "
            "FROM birth_profiles WHERE id = :pid"
        ),
        {"pid": profile.id.hex},
    ).one()

    encrypted_blobs = raw_row[:8]
    for blob in encrypted_blobs:
        assert isinstance(blob, bytes)
        assert blob.startswith(b"gAAAAA")

    joined_blobs = b"|".join(encrypted_blobs)
    for sensitive in (
        b"1998-07-31",
        b"08:30",
        b"27.7172",
        b"85.324",
        b"Asia/Kathmandu",
        "आशा जन्म".encode(),
        "काठमाडौं, नेपाल".encode(),
    ):
        assert sensitive not in joined_blobs

    assert raw_row[8] == "AD"
    assert raw_row[9] == "exact"


def test_birth_profile_check_constraints_and_fk_enforced(db_session: Session) -> None:
    """Database check constraints enforce valid enums, nullability pairs, and owner FK."""
    user = User(email="constraints@example.com", password_hash="hash")
    db_session.add(user)
    db_session.commit()

    # Valid BS unknown-time profile succeeds
    bs_unknown = _make_encrypted_profile(
        owner_id=user.id,
        input_calendar=InputCalendar.BS,
        entered_date="2055-04-15",
        date_ad=None,
        time_certainty=TimeCertainty.UNKNOWN,
        time_local=None,
    )
    db_session.add(bs_unknown)
    db_session.commit()

    # 1. Unknown time with non-null time_local_enc must fail
    bad_unknown = _make_encrypted_profile(
        owner_id=user.id,
        time_certainty=TimeCertainty.UNKNOWN,
        time_local="08:30",
    )
    db_session.add(bad_unknown)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 2. Exact time with null time_local_enc must fail
    bad_exact = _make_encrypted_profile(
        owner_id=user.id,
        time_certainty=TimeCertainty.EXACT,
        time_local=None,
    )
    db_session.add(bad_exact)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 3. Approximate time with null time_local_enc must fail
    bad_approx = _make_encrypted_profile(
        owner_id=user.id,
        time_certainty=TimeCertainty.APPROXIMATE,
        time_local=None,
    )
    db_session.add(bad_approx)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 4. BS calendar with non-null date_ad_enc must fail
    bad_bs = _make_encrypted_profile(
        owner_id=user.id,
        input_calendar=InputCalendar.BS,
        entered_date="2055-04-15",
        date_ad="1998-07-31",
    )
    db_session.add(bad_bs)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 5. AD calendar with null date_ad_enc must fail
    bad_ad = _make_encrypted_profile(
        owner_id=user.id,
        input_calendar=InputCalendar.AD,
        entered_date="1998-07-31",
        date_ad=None,
    )
    db_session.add(bad_ad)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 6. Unsupported input_calendar/time_certainty check constraints
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO birth_profiles "
                "(id, owner_id, label_enc, input_calendar, entered_date_enc, date_ad_enc, "
                "time_certainty, time_local_enc, place_name_enc, latitude_enc, longitude_enc, "
                "timezone_enc, created_at, updated_at) VALUES "
                "(:id, :owner_id, :b, 'LUNAR', :b, :b, 'exact', :b, :b, :b, :b, :b, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": uuid.uuid4().hex, "owner_id": user.id.hex, "b": b"enc"},
        )
        db_session.commit()
    db_session.rollback()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO birth_profiles "
                "(id, owner_id, label_enc, input_calendar, entered_date_enc, date_ad_enc, "
                "time_certainty, time_local_enc, place_name_enc, latitude_enc, longitude_enc, "
                "timezone_enc, created_at, updated_at) VALUES "
                "(:id, :owner_id, :b, 'AD', :b, :b, 'guessed', :b, :b, :b, :b, :b, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": uuid.uuid4().hex, "owner_id": user.id.hex, "b": b"enc"},
        )
        db_session.commit()
    db_session.rollback()

    # 7. Foreign key constraint rejects non-existent owner_id
    orphan = _make_encrypted_profile(owner_id=uuid.uuid4())
    db_session.add(orphan)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_user_birth_profiles_orm_and_db_on_delete_cascade(db_session: Session) -> None:
    """Verify both ORM delete-orphan/delete and SQL-level ON DELETE CASCADE remove profiles."""
    user_orm = User(email="orm_cascade@example.com", password_hash="hash")
    user_sql = User(email="sql_cascade@example.com", password_hash="hash")
    user_keep = User(email="keep@example.com", password_hash="hash")
    db_session.add_all([user_orm, user_sql, user_keep])
    db_session.commit()

    # 1. ORM delete-orphan via relationship collection
    orphan_candidate = _make_encrypted_profile(owner_id=user_orm.id, label="Orphan Test")
    user_orm.birth_profiles.append(orphan_candidate)
    db_session.commit()
    orphan_id = orphan_candidate.id
    assert db_session.get(BirthProfile, orphan_id) is not None

    user_orm.birth_profiles.clear()
    db_session.commit()
    assert db_session.get(BirthProfile, orphan_id) is None

    # 2. ORM User delete with unloaded relationship (passive_deletes + ON DELETE CASCADE)
    p_orm = _make_encrypted_profile(owner_id=user_orm.id, label="User Delete Test")
    db_session.add(p_orm)
    db_session.commit()
    p_orm_id = p_orm.id
    db_session.expire_all()

    db_session.delete(user_orm)
    db_session.commit()
    assert db_session.get(BirthProfile, p_orm_id) is None

    # 3. Direct SQL DELETE FROM users (database ON DELETE CASCADE without ORM interception)
    p_sql = _make_encrypted_profile(owner_id=user_sql.id, label="SQL Cascade Test")
    p_keep = _make_encrypted_profile(owner_id=user_keep.id, label="Preserved Profile")
    db_session.add_all([p_sql, p_keep])
    db_session.commit()
    p_sql_id = p_sql.id
    p_keep_id = p_keep.id
    db_session.expire_all()

    db_session.execute(delete(User).where(User.id == user_sql.id))
    db_session.commit()

    assert db_session.get(BirthProfile, p_sql_id) is None
    assert db_session.get(BirthProfile, p_keep_id) is not None


def test_alembic_discovery_and_offline_sql_generation() -> None:
    """Alembic env discovers all tables cleanly and generates offline upgrade/downgrade SQL."""
    assert {
        "users",
        "astrologer_profiles",
        "refresh_tokens",
        "password_reset_tokens",
        "audit_logs",
        "birth_profiles",
    }.issubset(set(Base.metadata.tables.keys()))

    alembic_ini = BACKEND_ROOT / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))

    script_dir = ScriptDirectory.from_config(cfg)
    heads = script_dir.get_heads()
    assert heads == ["0002_birth_profiles_table"]
    rev_0002 = script_dir.get_revision("0002_birth_profiles_table")
    assert rev_0002 is not None
    assert rev_0002.down_revision == "0001_initial_auth_tables"

    upgrade_buf = io.StringIO()
    cfg_up = Config(str(alembic_ini), stdout=upgrade_buf)
    cfg_up.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(cfg_up, "head", sql=True)
    upgrade_sql = upgrade_buf.getvalue()
    assert "CREATE TABLE birth_profiles" in upgrade_sql
    assert "ix_birth_profiles_owner_id" in upgrade_sql
    assert "ON DELETE CASCADE" in upgrade_sql
    assert "check_birth_profile_time_local_certainty" in upgrade_sql
    assert "check_birth_profile_calendar_date_ad" in upgrade_sql

    downgrade_buf = io.StringIO()
    cfg_down = Config(str(alembic_ini), stdout=downgrade_buf)
    cfg_down.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.downgrade(cfg_down, "0002_birth_profiles_table:0001_initial_auth_tables", sql=True)
    downgrade_sql = downgrade_buf.getvalue()
    assert "DROP INDEX" in downgrade_sql
    assert "DROP TABLE birth_profiles" in downgrade_sql


def test_profile_audit_allowlist_and_nested_pii_rejection(db_session: Session) -> None:
    """Profile audit logs enforce strict allowlist and strip nested PII or ciphertext."""
    user = User(email="audittest@example.com", password_hash="hash")
    db_session.add(user)
    db_session.commit()

    profile = _make_encrypted_profile(owner_id=user.id, label="Secret Person")
    db_session.add(profile)
    db_session.commit()

    # 1. Allowlist filters out disallowed keys, nested objects, bad enum values, and PII strings
    raw_dirty_meta = {
        "input_calendar": "AD",
        "time_certainty": "exact",
        "bs_conversion_status": "resolved",
        "changed_fields": ["place_name", "timezone", "1998-07-31", "Kathmandu", {"bad": 1}],
        "entered_date": "1998-07-31",
        "date_ad": "1998-07-31",
        "time_local": "08:30",
        "place_name": "Kathmandu, Nepal",
        "latitude": 27.7172,
        "longitude": 85.3240,
        "timezone": "Asia/Kathmandu",
        "label": "Secret Person",
        "label_enc": profile.label_enc,
        "nested_pii": {"birth_lat": 27.7, "birth_date": "1998-07-31"},
        "decrypted_object": profile,
    }
    clean_profile_meta = sanitize_profile_metadata(raw_dirty_meta)
    assert clean_profile_meta == {
        "input_calendar": "AD",
        "time_certainty": "exact",
        "bs_conversion_status": "resolved",
        "changed_fields": ["place_name", "timezone"],
    }

    # 2. Verify create / update / delete audit logs never store leaked values even if passed
    log_profile_action(
        db_session,
        action="profile:create",
        actor_id=user.id,
        profile_id=profile.id,
        metadata={
            "input_calendar": "BS",
            "time_certainty": "unknown",
            "bs_conversion_status": "awaiting_bs_conversion",
            "entered_date": "2055-04-15",
            "place_name": "Pokhara",
            "nested": {"latitude": 28.2096, "token": "secret"},
        },
    )
    log_profile_action(
        db_session,
        action="profile:update",
        actor_id=user.id,
        profile_id=profile.id,
        metadata={
            "input_calendar": "BS",
            "time_certainty": "approximate",
            "changed_fields": ["time_certainty", "time_local", "21:15"],
            "time_local": "21:15",
        },
    )
    # Direct log_action call on profile:* must also enforce the allowlist
    log_action(
        db_session,
        action="profile:delete",
        actor_id=user.id,
        target_type="birth_profile",
        target_id=str(profile.id),
        metadata={
            "input_calendar": "BS",
            "time_certainty": "approximate",
            "arbitrary_unlisted_key": "should-never-persist",
            "timezone": "Asia/Kathmandu",
        },
    )
    db_session.commit()

    entries = db_session.scalars(
        select(AuditLog).where(AuditLog.target_type == "birth_profile")
    ).all()
    assert len(entries) == 3

    serialized = json.dumps([e.event_metadata for e in entries])
    for forbidden_value in (
        "2055-04-15",
        "Pokhara",
        "28.2096",
        "21:15",
        "should-never-persist",
        "Asia/Kathmandu",
        "Secret Person",
        "gAAAAA",
    ):
        assert forbidden_value not in serialized

    by_action = {e.action: e.event_metadata for e in entries}
    assert by_action["profile:create"] == {
        "input_calendar": "BS",
        "time_certainty": "unknown",
        "bs_conversion_status": "awaiting_bs_conversion",
    }
    assert by_action["profile:update"] == {
        "input_calendar": "BS",
        "time_certainty": "approximate",
        "changed_fields": ["time_certainty", "time_local"],
    }
    assert by_action["profile:delete"] == {
        "input_calendar": "BS",
        "time_certainty": "approximate",
    }

    # 3. Recursive sanitize_metadata drops nested PII, Fernet tokens, bytes, and ORM objects
    nested_dirty = {
        "ok": "kept",
        "nested": {
            "latitude": 27.7172,
            "deeper": {"place_name": "Lalitpur", "count": 2},
            "password": "hidden",
        },
        "items": [
            {"longitude": 85.3, "note": "safe"},
            {"birth_datetime": "1998-07-31T08:30"},
        ],
        "fernet_under_benign_key": profile.label_enc.decode("ascii"),
        "raw_bytes": b"secret-bytes",
        "orm_obj": profile,
    }
    cleaned_general = sanitize_metadata(nested_dirty)
    assert cleaned_general == {
        "ok": "kept",
        "nested": {"deeper": {"count": 2}},
        "items": [{"note": "safe"}],
    }
