"""Integration tests for authenticated birth profile CRUD, privacy, and isolation."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.permissions import ROLE_PERMISSIONS, Permission, UserRole
from app.core.security import encrypt_text
from app.db.models import AstrologerStatus, AuditLog, BirthProfile


def _auth_headers(
    client: TestClient, email: str, password: str = "TestPassword2026!"
) -> dict[str, str]:
    """Authenticate an existing user and return Bearer authorization headers."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ad_payload(**overrides: object) -> dict[str, object]:
    """Return a valid AD exact birth profile payload."""
    payload: dict[str, object] = {
        "label": "Asha Sharma",
        "input_calendar": "AD",
        "entered_date": "1998-07-31",
        "time_certainty": "exact",
        "time_local": "08:30",
        "place_name": "Kathmandu, Nepal",
        "latitude": 27.7172,
        "longitude": 85.3240,
        "timezone": "Asia/Kathmandu",
    }
    payload.update(overrides)
    return payload


def test_profiles_require_authentication_and_permission(
    client: TestClient,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unauthenticated callers receive 401 and missing permission returns 403."""
    sample_id = str(uuid.uuid4())
    assert client.post("/api/v1/profiles", json=_ad_payload()).status_code == 401
    assert client.get("/api/v1/profiles").status_code == 401
    assert client.get(f"/api/v1/profiles/{sample_id}").status_code == 401
    assert (
        client.patch(f"/api/v1/profiles/{sample_id}", json={"label": "Updated"}).status_code == 401
    )
    assert client.delete(f"/api/v1/profiles/{sample_id}").status_code == 401

    user_factory(email="noperms@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "noperms@example.com")

    # Simulate role without Permission.PROFILE_MANAGE_OWN
    reduced_perms = ROLE_PERMISSIONS[UserRole.USER] - {Permission.PROFILE_MANAGE_OWN}
    monkeypatch.setitem(ROLE_PERMISSIONS, UserRole.USER, reduced_perms)

    assert client.get("/api/v1/profiles", headers=headers).status_code == 403
    assert client.post("/api/v1/profiles", json=_ad_payload(), headers=headers).status_code == 403


def test_full_crud_lifecycle_and_encrypted_persistence(
    client: TestClient,
    db_session: Session,
    user_factory: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify create, list pagination, get, patch, delete, DB ciphertext, and audit hygiene."""
    caplog.set_level(logging.DEBUG)

    user = user_factory(email="asha@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "asha@example.com")

    # 1. Create AD profile
    create_1 = client.post("/api/v1/profiles", json=_ad_payload(), headers=headers)
    assert create_1.status_code == 201
    data_1 = create_1.json()
    assert data_1["owner_id"] == str(user.id)
    assert data_1["label"] == "Asha Sharma"
    assert data_1["input_calendar"] == "AD"
    assert data_1["entered_date"] == "1998-07-31"
    assert data_1["date_ad"] == "1998-07-31"
    assert data_1["bs_conversion_status"] == "resolved"
    assert data_1["time_certainty"] == "exact"
    assert data_1["time_local"] == "08:30"
    assert data_1["place_name"] == "Kathmandu, Nepal"
    assert data_1["latitude"] == 27.7172
    assert data_1["longitude"] == 85.3240
    assert data_1["timezone"] == "Asia/Kathmandu"
    assert not any(key.endswith("_enc") for key in data_1)

    profile_id = data_1["id"]

    # Inspect raw SQLite columns to ensure all sensitive values are encrypted at rest
    raw_row = db_session.execute(
        text(
            "SELECT label_enc, entered_date_enc, date_ad_enc, time_local_enc, "
            "place_name_enc, latitude_enc, longitude_enc, timezone_enc "
            "FROM birth_profiles WHERE id = :pid"
        ),
        {"pid": uuid.UUID(profile_id).hex},
    ).one()
    for blob in raw_row:
        assert isinstance(blob, bytes)
        assert blob.startswith(b"gAAAAA")
    raw_joined = b"|".join(raw_row)
    for sensitive_bytes in (
        b"Asha Sharma",
        b"1998-07-31",
        b"08:30",
        b"Kathmandu, Nepal",
        b"27.7172",
        b"85.324",
        b"Asia/Kathmandu",
    ):
        assert sensitive_bytes not in raw_joined

    # 2. Create second profile (BS pending, unknown time) and verify pagination
    create_2 = client.post(
        "/api/v1/profiles",
        json={
            "label": "Bikram Sample",
            "input_calendar": "BS",
            "entered_date": "2055-04-15",
            "time_certainty": "unknown",
            "time_local": None,
            "place_name": "Pokhara, Nepal",
            "latitude": 28.2096,
            "longitude": 83.9856,
            "timezone": "Asia/Kathmandu",
        },
        headers=headers,
    )
    assert create_2.status_code == 201
    data_2 = create_2.json()
    assert data_2["input_calendar"] == "BS"
    assert data_2["entered_date"] == "2055-04-15"
    assert data_2["date_ad"] is None
    assert data_2["bs_conversion_status"] == "awaiting_bs_conversion"
    assert data_2["time_certainty"] == "unknown"
    assert data_2["time_local"] is None

    list_page_1 = client.get("/api/v1/profiles?limit=1&offset=0", headers=headers)
    assert list_page_1.status_code == 200
    assert list_page_1.json()["total"] == 2
    assert len(list_page_1.json()["items"]) == 1

    list_page_2 = client.get("/api/v1/profiles?limit=1&offset=1", headers=headers)
    assert list_page_2.status_code == 200
    assert len(list_page_2.json()["items"]) == 1
    assert list_page_1.json()["items"][0]["id"] != list_page_2.json()["items"][0]["id"]

    # 3. Get single profile
    get_resp = client.get(f"/api/v1/profiles/{profile_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["label"] == "Asha Sharma"

    # 4. Partial update (PATCH)
    patch_resp = client.patch(
        f"/api/v1/profiles/{profile_id}",
        json={"label": "Asha Updated", "place_name": "Lalitpur, Nepal"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["label"] == "Asha Updated"
    assert patched["place_name"] == "Lalitpur, Nepal"
    assert patched["entered_date"] == "1998-07-31"
    assert patched["time_local"] == "08:30"

    # 5. Delete profile and confirm hard deletion
    del_resp = client.delete(f"/api/v1/profiles/{profile_id}", headers=headers)
    assert del_resp.status_code == 204
    assert del_resp.content == b""

    after_del = client.get(f"/api/v1/profiles/{profile_id}", headers=headers)
    assert after_del.status_code == 404
    assert db_session.get(BirthProfile, uuid.UUID(profile_id)) is None

    # 6. Audit logs contain only allowlisted metadata, never PII or ciphertext
    audit_rows = db_session.scalars(
        select(AuditLog).where(AuditLog.target_type == "birth_profile")
    ).all()
    assert len(audit_rows) == 4  # 2 creates, 1 update, 1 delete
    audit_json = json.dumps([row.event_metadata for row in audit_rows])
    for leaked_candidate in (
        "Asha",
        "Bikram",
        "1998-07-31",
        "2055-04-15",
        "08:30",
        "Kathmandu",
        "Lalitpur",
        "Pokhara",
        "27.7172",
        "85.324",
        "Asia/Kathmandu",
        "gAAAAA",
    ):
        assert leaked_candidate not in audit_json
    log_text = caplog.text
    for leaked_candidate in (
        "Asha Sharma",
        "Asha Updated",
        "1998-07-31",
        "2055-04-15",
        "Kathmandu, Nepal",
        "Lalitpur, Nepal",
        "Pokhara, Nepal",
        "gAAAAA",
    ):
        assert leaked_candidate not in log_text


def test_cross_user_ownership_isolation_returns_404_even_for_admin_and_astrologer(
    client: TestClient,
    user_factory: Any,
) -> None:
    """Another user, astrologer, or admin accessing a profile receives 404 without listing it."""
    user_factory(email="owner@example.com", role=UserRole.USER)
    user_factory(email="other@example.com", role=UserRole.USER)
    user_factory(
        email="astro@example.com",
        role=UserRole.ASTROLOGER,
        astrologer_status=AstrologerStatus.APPROVED,
    )
    user_factory(email="admin@example.com", role=UserRole.ADMIN)

    owner_headers = _auth_headers(client, "owner@example.com")
    create_resp = client.post("/api/v1/profiles", json=_ad_payload(), headers=owner_headers)
    assert create_resp.status_code == 201
    profile_id = create_resp.json()["id"]

    for intruder_email in ("other@example.com", "astro@example.com", "admin@example.com"):
        intruder_headers = _auth_headers(client, intruder_email)
        list_resp = client.get("/api/v1/profiles", headers=intruder_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 0
        assert list_resp.json()["items"] == []

        assert (
            client.get(f"/api/v1/profiles/{profile_id}", headers=intruder_headers).status_code
            == 404
        )
        assert (
            client.patch(
                f"/api/v1/profiles/{profile_id}",
                json={"label": "Tamper"},
                headers=intruder_headers,
            ).status_code
            == 404
        )
        assert (
            client.delete(f"/api/v1/profiles/{profile_id}", headers=intruder_headers).status_code
            == 404
        )

    # Owner can still read intact profile
    assert client.get(f"/api/v1/profiles/{profile_id}", headers=owner_headers).status_code == 200


def test_time_certainty_and_calendar_patch_transitions(
    client: TestClient,
    user_factory: Any,
) -> None:
    """PATCH validates transitions across exact, approximate, unknown, AD, and BS modes."""
    user_factory(email="transitions@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "transitions@example.com")

    created = client.post("/api/v1/profiles", json=_ad_payload(), headers=headers)
    assert created.status_code == 201
    pid = created.json()["id"]

    # exact -> unknown clears time_local cleanly
    to_unknown = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"time_certainty": "unknown"},
        headers=headers,
    )
    assert to_unknown.status_code == 200
    assert to_unknown.json()["time_certainty"] == "unknown"
    assert to_unknown.json()["time_local"] is None

    # Supplying time_local while remaining unknown fails with 422
    bad_add_time = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"time_local": "09:15"},
        headers=headers,
    )
    assert bad_add_time.status_code == 422
    assert "09:15" not in bad_add_time.text

    # Switching from unknown to approximate without time_local fails with 422
    bad_approx = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"time_certainty": "approximate"},
        headers=headers,
    )
    assert bad_approx.status_code == 422

    # Switching from unknown to approximate with time_local succeeds
    to_approx = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"time_certainty": "approximate", "time_local": "09:15"},
        headers=headers,
    )
    assert to_approx.status_code == 200
    assert to_approx.json()["time_certainty"] == "approximate"
    assert to_approx.json()["time_local"] == "09:15"

    # Conflicting certainty="unknown" + non-null time_local fails with 422
    conflict_unknown = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"time_certainty": "unknown", "time_local": "09:15"},
        headers=headers,
    )
    assert conflict_unknown.status_code == 422
    assert "09:15" not in conflict_unknown.text

    # Clearing time_local to null without setting certainty="unknown" fails with 422
    bad_clear_time = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"time_local": None},
        headers=headers,
    )
    assert bad_clear_time.status_code == 422

    # Switching AD -> BS clears date_ad and sets awaiting_bs_conversion
    to_bs = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"input_calendar": "BS", "entered_date": "2055-04-32"},
        headers=headers,
    )
    assert to_bs.status_code == 200
    assert to_bs.json()["input_calendar"] == "BS"
    assert to_bs.json()["entered_date"] == "2055-04-32"
    assert to_bs.json()["date_ad"] is None
    assert to_bs.json()["bs_conversion_status"] == "awaiting_bs_conversion"

    # Attempting BS -> AD without changing invalid Gregorian day 32 fails on merged state
    bad_bs_to_ad = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"input_calendar": "AD"},
        headers=headers,
    )
    assert bad_bs_to_ad.status_code == 422
    assert "2055-04-32" not in bad_bs_to_ad.text


def test_timezone_dst_and_coordinate_validation_with_pii_free_422_responses(
    client: TestClient,
    user_factory: Any,
) -> None:
    """HTTP 422 errors validate timezone/DST/coordinates without echoing submitted PII."""
    user_factory(email="dst@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "dst@example.com")

    # Region-based IANA and UTC succeed
    for tz_name in ("Asia/Kathmandu", "Europe/London", "UTC"):
        ok_resp = client.post(
            "/api/v1/profiles",
            json=_ad_payload(timezone=tz_name, label=f"Profile {tz_name}"),
            headers=headers,
        )
        assert ok_resp.status_code == 201

    # Abbreviations & invalid timezones fail without reflecting submitted PII
    secret_label = "Confidential Birth Person"
    secret_place = "Hidden Village 42"
    for bad_tz in ("EST", "NPT", "Invalid/Zone"):
        bad_resp = client.post(
            "/api/v1/profiles",
            json=_ad_payload(
                label=secret_label,
                place_name=secret_place,
                entered_date="1997-05-19",
                time_local="11:45",
                timezone=bad_tz,
            ),
            headers=headers,
        )
        assert bad_resp.status_code == 422
        body = bad_resp.text
        for detail_item in bad_resp.json()["detail"]:
            assert "input" not in detail_item
            assert "ctx" not in detail_item
        for pii in (secret_label, secret_place, "1997-05-19", "11:45", bad_tz, "27.7172", "85.324"):
            assert pii not in body

    # POST DST gap (spring forward) and DST overlap (fall back) fail without PII reflection
    for dst_date, dst_time in (("2024-03-10", "02:30"), ("2024-11-03", "01:30")):
        dst_resp = client.post(
            "/api/v1/profiles",
            json=_ad_payload(
                label=secret_label,
                entered_date=dst_date,
                time_local=dst_time,
                place_name=secret_place,
                latitude=40.7128,
                longitude=-74.0060,
                timezone="America/New_York",
            ),
            headers=headers,
        )
        assert dst_resp.status_code == 422
        body = dst_resp.text
        for pii in (secret_label, secret_place, dst_date, dst_time, "America/New_York", "40.7128"):
            assert pii not in body

    # Unknown birth time on DST gap date succeeds
    unknown_dst_ok = client.post(
        "/api/v1/profiles",
        json=_ad_payload(
            entered_date="2024-03-10",
            time_certainty="unknown",
            time_local=None,
            latitude=40.7128,
            longitude=-74.0060,
            timezone="America/New_York",
        ),
        headers=headers,
    )
    assert unknown_dst_ok.status_code == 201

    # Moving valid NY profile time into DST gap via PATCH fails without PII leakage
    valid_ny = client.post(
        "/api/v1/profiles",
        json=_ad_payload(
            entered_date="2024-03-10",
            time_certainty="exact",
            time_local="01:15",
            latitude=40.7128,
            longitude=-74.0060,
            timezone="America/New_York",
        ),
        headers=headers,
    )
    assert valid_ny.status_code == 201
    ny_id = valid_ny.json()["id"]

    patch_gap = client.patch(
        f"/api/v1/profiles/{ny_id}",
        json={"time_local": "02:30"},
        headers=headers,
    )
    assert patch_gap.status_code == 422
    assert "02:30" not in patch_gap.text

    # Out-of-bounds coordinates fail without reflecting value
    bad_coords = client.post(
        "/api/v1/profiles",
        json=_ad_payload(latitude=95.1234, longitude=-181.5678),
        headers=headers,
    )
    assert bad_coords.status_code == 422
    assert "95.1234" not in bad_coords.text
    assert "-181.5678" not in bad_coords.text


def test_corrupted_ciphertext_never_leaks_internal_crypto_errors(
    client: TestClient,
    db_session: Session,
    user_factory: Any,
) -> None:
    """Ciphertext tampering yields an opaque 500 without exposing ciphertext or key internals."""
    user_factory(email="corrupt@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "corrupt@example.com")

    created = client.post("/api/v1/profiles", json=_ad_payload(), headers=headers)
    assert created.status_code == 201
    pid = uuid.UUID(created.json()["id"])

    record = db_session.get(BirthProfile, pid)
    assert record is not None
    wrong_key = Fernet.generate_key().decode("ascii")
    wrong_key_blob = encrypt_text("Tampered Value", wrong_key)
    record.place_name_enc = wrong_key_blob
    db_session.commit()

    resp = client.get(f"/api/v1/profiles/{pid}", headers=headers)
    assert resp.status_code == 500
    assert "Unable to load birth profile" in resp.text
    assert "InvalidToken" not in resp.text
    assert "gAAAAA" not in resp.text
    assert wrong_key not in resp.text
