"""Integration tests for POST /api/v1/profiles/{profile_id}/chart API contract."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

import app.calc.facts as calc_facts_mod
import app.services.chart_service as chart_service_mod
from app.api.schemas.chart import ChartCalculationResponse
from app.calc.ayanamsha import CalculationError
from app.calc.ephemeris import EphemerisSource
from app.calc.facts import ENGINE_VERSION, ChartFactSensitivity, ChartSettings, compute_chart_facts
from app.calc.timeconv import TimeConversionError, TimeInput
from app.core.config import Settings
from app.core.permissions import ROLE_PERMISSIONS, Permission, UserRole
from app.core.security import (
    create_access_token,
    encrypt_optional_text,
    encrypt_text,
)
from app.db.models import AstrologerStatus, AuditLog, BirthProfile


def _auth_headers(
    client: TestClient, email: str, password: str = "TestPassword2026!"
) -> dict[str, str]:
    """Authenticate an existing user and return Bearer headers."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_profile(
    client: TestClient,
    headers: dict[str, str],
    **overrides: object,
) -> dict[str, Any]:
    """Create a real encrypted birth profile through POST /api/v1/profiles."""
    payload: dict[str, object] = {
        "label": "Fixture 001 Birth",
        "input_calendar": "AD",
        "entered_date": "2006-08-02",
        "time_certainty": "exact",
        "time_local": "02:10",
        "place_name": "Morang, Nepal",
        "latitude": 26.45,
        "longitude": 87.283,
        "timezone": "Asia/Kathmandu",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/profiles", json=payload, headers=headers)
    assert resp.status_code == 201
    return dict(resp.json())


def test_chart_endpoint_success_determinism_settings_and_no_persistence(
    client: TestClient,
    db_session: Session,
    user_factory: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Authenticated owner receives deterministic ChartFacts without persisting chart rows."""
    caplog.set_level(logging.DEBUG)

    user_factory(email="chartowner@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "chartowner@example.com")

    created = _create_profile(client, headers)
    pid = created["id"]
    initial_updated_at = created["updated_at"]

    # Snapshot AuditLog count and verify no chart persistence table is written
    audit_count_before = db_session.scalar(select(func.count(AuditLog.id))) or 0

    # Commit-guard: chart endpoint must not call Session.commit or add rows
    orig_commit = db_session.commit
    commit_calls = 0

    def _counting_commit(*args: Any, **kwargs: Any) -> Any:
        nonlocal commit_calls
        commit_calls += 1
        return orig_commit(*args, **kwargs)

    db_session.commit = _counting_commit  # type: ignore[method-assign]
    try:
        # 1. Default calculation with empty JSON {} and completely omitted body match byte-for-byte
        resp_1 = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
        resp_2 = client.post(f"/api/v1/profiles/{pid}/chart", headers=headers)
        assert resp_1.status_code == 200
        assert resp_2.status_code == 200
        assert resp_1.headers.get("cache-control") == "no-store"
        assert resp_2.headers.get("cache-control") == "no-store"
        assert resp_1.text == resp_2.text

        parsed = ChartCalculationResponse.model_validate(resp_1.json())
        assert str(parsed.profile_id) == pid
        assert parsed.input_calendar.value == "AD"
        assert parsed.time_certainty.value == "exact"
        assert parsed.chart.engine_version == ENGINE_VERSION
        assert parsed.chart.chart_id.startswith("c_")
        assert parsed.chart.metadata.ephemeris_source in ("swieph", "moshier", "mixed")
        fact_ids = [f.id for f in parsed.chart.facts]
        assert fact_ids[:10] == [
            "f_lagna",
            "f_sun",
            "f_moon",
            "f_mars",
            "f_mercury",
            "f_jupiter",
            "f_venus",
            "f_saturn",
            "f_rahu",
            "f_ketu",
        ]
        # Fixture 001 sanity: Moon in Libra, Swati, Pada 1
        moon_fact = next(f for f in parsed.chart.facts if f.id == "f_moon")
        assert moon_fact.sign == "Libra"
        assert moon_fact.nakshatra == "Swati"
        assert moon_fact.pada == 1

        # Envelope omits unused encrypted identity fields (label, place_name, entered_date)
        raw_json = resp_1.json()
        assert "label" not in raw_json
        assert "place_name" not in raw_json
        assert "Fixture 001 Birth" not in resp_1.text
        assert "Morang, Nepal" not in resp_1.text

        # 2. Named preset + explicit year_days updates settings & chart_id consistently
        hamro_resp = client.post(
            f"/api/v1/profiles/{pid}/chart",
            json={"preset": "hamro_patro_compat", "year_days": 360},
            headers=headers,
        )
        assert hamro_resp.status_code == 200
        hamro_data = ChartCalculationResponse.model_validate(hamro_resp.json())
        assert hamro_data.chart.settings.ayanamsha.value == "lahiri_1940"
        assert hamro_data.chart.settings.node_type.value == "true"
        assert hamro_data.chart.settings.preset == "hamro_patro_compat"
        assert hamro_data.chart.settings.year_days == 360.0
        assert hamro_data.chart.chart_id != parsed.chart.chart_id

        # 3. Changing only year_days changes both settings and chart_id
        days_resp = client.post(
            f"/api/v1/profiles/{pid}/chart",
            json={"year_days": 365.2425},
            headers=headers,
        )
        assert days_resp.status_code == 200
        days_data = ChartCalculationResponse.model_validate(days_resp.json())
        assert days_data.chart.settings.year_days == 365.2425
        assert days_data.chart.chart_id != parsed.chart.chart_id

        assert commit_calls == 0
        assert not db_session.new
        assert not db_session.dirty
        assert not db_session.deleted
    finally:
        db_session.commit = orig_commit  # type: ignore[method-assign]

    audit_count_after = db_session.scalar(select(func.count(AuditLog.id))) or 0
    assert audit_count_after == audit_count_before

    db_record = db_session.get(BirthProfile, uuid.UUID(pid))
    assert db_record is not None
    parsed_initial = datetime.fromisoformat(initial_updated_at)
    expected_updated_at = (
        parsed_initial.astimezone(UTC)
        if parsed_initial.tzinfo is not None
        else parsed_initial.replace(tzinfo=UTC)
    )
    recorded_updated_at = (
        db_record.updated_at.astimezone(UTC)
        if db_record.updated_at.tzinfo is not None
        else db_record.updated_at.replace(tzinfo=UTC)
    )
    assert recorded_updated_at == expected_updated_at

    # Zero sensitive data or Fernet ciphertext in logs
    for leaked in ("Fixture 001 Birth", "2006-08-02", "02:10", "Morang", "87.283", "gAAAAA"):
        assert leaked not in caplog.text


def test_chart_endpoint_approximate_time_and_lagna_sensitivity(
    client: TestClient,
    user_factory: Any,
) -> None:
    """Approximate certainty is preserved; near-boundary Lagna emits f_lagna_sensitivity."""
    user_factory(email="approx@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "approx@example.com")

    # 2006-08-02 01:57 Asia/Kathmandu produces Taurus ~29.566 deg (within 0.5 deg boundary)
    boundary_profile = _create_profile(
        client,
        headers,
        label="Boundary Approx",
        entered_date="2006-08-02",
        time_certainty="approximate",
        time_local="01:57",
    )
    resp = client.post(
        f"/api/v1/profiles/{boundary_profile['id']}/chart",
        json={},
        headers=headers,
    )
    assert resp.status_code == 200
    parsed = ChartCalculationResponse.model_validate(resp.json())
    assert parsed.time_certainty.value == "approximate"
    sens_facts = [f for f in parsed.chart.facts if isinstance(f, ChartFactSensitivity)]
    assert len(sens_facts) == 1
    assert sens_facts[0].id == "f_lagna_sensitivity"
    assert sens_facts[0].boundary_distance_degrees < 0.5


def test_chart_endpoint_auth_rbac_and_cross_user_isolation(
    client: TestClient,
    user_factory: Any,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enforce 401 auth, CHART_READ_OWN without PROFILE_MANAGE_OWN, 403, and 404 isolation."""
    owner = user_factory(email="iso_owner@example.com", role=UserRole.USER)
    inactive = user_factory(email="iso_inactive@example.com", role=UserRole.USER, is_active=False)
    user_factory(email="iso_other@example.com", role=UserRole.USER)
    user_factory(
        email="iso_astro@example.com",
        role=UserRole.ASTROLOGER,
        astrologer_status=AstrologerStatus.APPROVED,
    )
    user_factory(email="iso_admin@example.com", role=UserRole.ADMIN)

    owner_headers = _auth_headers(client, "iso_owner@example.com")
    pid = _create_profile(client, owner_headers)["id"]

    # 1. Missing, invalid, expired, and deactivated-user JWT tokens return 401
    assert client.post(f"/api/v1/profiles/{pid}/chart", json={}).status_code == 401
    assert (
        client.post(
            f"/api/v1/profiles/{pid}/chart",
            json={},
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        ).status_code
        == 401
    )
    expired_token = create_access_token(
        subject=str(owner.id),
        role=owner.role.value,
        secret=test_settings.JWT_SECRET,
        expires_delta=timedelta(minutes=-5),
    )
    assert (
        client.post(
            f"/api/v1/profiles/{pid}/chart",
            json={},
            headers={"Authorization": f"Bearer {expired_token}"},
        ).status_code
        == 401
    )
    inactive_token = create_access_token(
        subject=str(inactive.id),
        role=inactive.role.value,
        secret=test_settings.JWT_SECRET,
        expires_delta=timedelta(minutes=5),
    )
    assert (
        client.post(
            f"/api/v1/profiles/{pid}/chart",
            json={},
            headers={"Authorization": f"Bearer {inactive_token}"},
        ).status_code
        == 401
    )

    # 2. Cross-user, approved astrologer, and admin access all fail with 404 anti-enumeration
    for intruder in ("iso_other@example.com", "iso_astro@example.com", "iso_admin@example.com"):
        intruder_headers = _auth_headers(client, intruder)
        intruder_resp = client.post(
            f"/api/v1/profiles/{pid}/chart",
            json={},
            headers=intruder_headers,
        )
        assert intruder_resp.status_code == 404
        assert intruder_resp.json() == {"detail": "Item not found"}

    # Non-existent UUID returns 404
    missing_resp = client.post(
        f"/api/v1/profiles/{uuid.uuid4()}/chart",
        json={},
        headers=owner_headers,
    )
    assert missing_resp.status_code == 404

    # 3. CHART_READ_OWN works even when PROFILE_MANAGE_OWN is absent
    only_chart_perms = ROLE_PERMISSIONS[UserRole.USER] - {Permission.PROFILE_MANAGE_OWN}
    monkeypatch.setitem(ROLE_PERMISSIONS, UserRole.USER, only_chart_perms)
    assert (
        client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=owner_headers).status_code
        == 200
    )

    # 4. Missing CHART_READ_OWN returns 403
    no_chart_perms = ROLE_PERMISSIONS[UserRole.USER] - {Permission.CHART_READ_OWN}
    monkeypatch.setitem(ROLE_PERMISSIONS, UserRole.USER, no_chart_perms)
    assert (
        client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=owner_headers).status_code
        == 403
    )


def test_chart_endpoint_409_blocked_states_without_calc_invocation(
    client: TestClient,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BS and unknown-time profiles return 409 Conflict with codes and zero engine calls."""
    user_factory(email="blocked@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "blocked@example.com")

    bs_profile = _create_profile(
        client,
        headers,
        label="BS Profile",
        input_calendar="BS",
        entered_date="2055-04-15",
        time_certainty="exact",
        time_local="08:30",
    )
    unknown_profile = _create_profile(
        client,
        headers,
        label="Unknown Time Profile",
        input_calendar="AD",
        entered_date="2000-05-10",
        time_certainty="unknown",
        time_local=None,
    )

    def _forbid(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("compute_chart_facts must not be called for blocked profiles")

    monkeypatch.setattr(chart_service_mod, "compute_chart_facts", _forbid)

    bs_resp = client.post(
        f"/api/v1/profiles/{bs_profile['id']}/chart",
        json={},
        headers=headers,
    )
    assert bs_resp.status_code == 409
    assert bs_resp.headers.get("cache-control") == "no-store"
    assert bs_resp.json()["code"] == "AWAITING_BS_CONVERSION"
    assert "2055-04-15" not in bs_resp.text

    unk_resp = client.post(
        f"/api/v1/profiles/{unknown_profile['id']}/chart",
        json={},
        headers=headers,
    )
    assert unk_resp.status_code == 409
    assert unk_resp.headers.get("cache-control") == "no-store"
    assert unk_resp.json()["code"] == "UNKNOWN_TIME_UNSUPPORTED"
    assert "2000-05-10" not in unk_resp.text


def test_chart_endpoint_sanitized_422_validation_and_synthetic_isolation(
    client: TestClient,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid settings, birth overrides, synthetic IDs, and DST transitions return 422."""
    user_factory(email="val422@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "val422@example.com")
    pid = _create_profile(client, headers)["id"]

    # Non-UUID synthetic ID / invalid ID path fails 422
    synth_resp = client.post(
        "/api/v1/profiles/sample_north_london/chart",
        json={},
        headers=headers,
    )
    assert synth_resp.status_code == 422
    for item in synth_resp.json()["detail"]:
        assert "input" not in item
        assert "ctx" not in item

    # Client birth overrides and bad settings fail 422 without input/ctx leakage
    bad_bodies: list[dict[str, object]] = [
        {"date": "1990-01-01", "time_local": "12:00"},
        {"latitude": 51.5, "longitude": -0.1},
        {"year_days": 366},
        {"preset": "not_a_preset"},
        {"preset": "hamro_patro_compat", "ayanamsha": "raman"},
        {"house_system": "placidus"},
        {"ayanamsha": None},
    ]
    for payload in bad_bodies:
        resp = client.post(f"/api/v1/profiles/{pid}/chart", json=payload, headers=headers)
        assert resp.status_code == 422
        body = resp.text
        for item in resp.json()["detail"]:
            assert "input" not in item
            assert "ctx" not in item
        assert "1990-01-01" not in body
        assert "not_a_preset" not in body
        assert "placidus" not in body

    # Known TimeConversionError during calculation maps to sanitized 422
    def _raise_overlap(*_args: Any, **_kwargs: Any) -> Any:
        raise TimeConversionError(
            "Ambiguous local time in DST overlap: 2006-08-02 02:10 in Asia/Kathmandu",
            code="dst_overlap",
        )

    monkeypatch.setattr(chart_service_mod, "compute_chart_facts", _raise_overlap)
    dst_resp = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
    assert dst_resp.status_code == 422
    assert dst_resp.headers.get("cache-control") == "no-store"
    assert dst_resp.json()["code"] == "dst_overlap"
    assert "2006-08-02" not in dst_resp.text
    assert "02:10" not in dst_resp.text
    assert "Asia/Kathmandu" not in dst_resp.text


def test_chart_endpoint_decryption_calc_and_unexpected_500_fail_closed(
    client: TestClient,
    db_session: Session,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decryption corruption, CalculationError, and unexpected errors return opaque 500."""
    user_factory(email="fail500@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "fail500@example.com")
    pid = _create_profile(client, headers)["id"]

    # 1. CalculationError -> opaque 500
    monkeypatch.setattr(
        chart_service_mod,
        "compute_chart_facts",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            CalculationError("swe_calc_ut error status=-1 secret_coord=26.45")
        ),
    )
    calc_err_resp = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
    assert calc_err_resp.status_code == 500
    assert calc_err_resp.headers.get("cache-control") == "no-store"
    assert calc_err_resp.json() == {"detail": "Unable to compute birth chart"}
    assert "26.45" not in calc_err_resp.text
    assert "swe_calc_ut" not in calc_err_resp.text

    # 2. Unexpected internal exceptions (ValueError / RuntimeError) -> opaque 500
    monkeypatch.setattr(
        chart_service_mod,
        "compute_chart_facts",
        lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("unexpected traceback secret")),
    )
    unexp_resp = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
    assert unexp_resp.status_code == 500
    assert unexp_resp.json() == {"detail": "Unable to compute birth chart"}
    assert "unexpected traceback" not in unexp_resp.text

    monkeypatch.setattr(
        chart_service_mod,
        "compute_chart_facts",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("internal secret crash")),
    )
    runtime_resp = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
    assert runtime_resp.status_code == 500
    assert runtime_resp.json() == {"detail": "Unable to compute birth chart"}
    assert "internal secret crash" not in runtime_resp.text

    # 3. Corrupted Fernet ciphertext in birth_profiles -> opaque 500 without leaking crypto details
    monkeypatch.setattr(chart_service_mod, "compute_chart_facts", compute_chart_facts)
    record = db_session.get(BirthProfile, uuid.UUID(pid))
    assert record is not None
    wrong_key = Fernet.generate_key().decode("ascii")
    record.date_ad_enc = encrypt_optional_text("2006-08-02", wrong_key)
    db_session.commit()

    decrypt_err_resp = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
    assert decrypt_err_resp.status_code == 500
    assert decrypt_err_resp.headers.get("cache-control") == "no-store"
    assert decrypt_err_resp.json() == {"detail": "Unable to compute birth chart"}
    assert "InvalidToken" not in decrypt_err_resp.text
    assert "gAAAAA" not in decrypt_err_resp.text
    assert wrong_key not in decrypt_err_resp.text


def test_chart_endpoint_handles_mixed_ephemeris_provenance(
    client: TestClient,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API preserves swieph, moshier, and mixed provenance verbatim from calc engine."""
    user_factory(email="prov@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "prov@example.com")
    pid = _create_profile(client, headers)["id"]

    orig_calc = calc_facts_mod.compute_chart_facts

    def _make_source_variant(source: EphemerisSource) -> Any:
        def _wrapped(birth_input: TimeInput, settings: ChartSettings, chart_id: str) -> Any:
            doc = orig_calc(birth_input, settings, chart_id)
            updated_meta = doc.metadata.model_copy(update={"ephemeris_source": source})
            return doc.model_copy(update={"metadata": updated_meta})

        return _wrapped

    for expected_source in ("swieph", "moshier", "mixed"):
        monkeypatch.setattr(
            chart_service_mod, "compute_chart_facts", _make_source_variant(expected_source)
        )
        resp = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["chart"]["metadata"]["ephemeris_source"] == expected_source


def test_chart_endpoint_profile_edit_updates_chart_id_deterministically(
    client: TestClient,
    db_session: Session,
    user_factory: Any,
) -> None:
    """Updating a birth profile rotates updated_at and produces a distinct chart_id."""
    user_factory(email="edit_chart@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "edit_chart@example.com")
    created = _create_profile(client, headers)
    pid = created["id"]

    r1 = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
    assert r1.status_code == 200
    cid_1 = r1.json()["chart"]["chart_id"]

    # Advance updated_at cleanly and re-encrypt time_local via real PATCH endpoint
    row = db_session.get(BirthProfile, uuid.UUID(pid))
    assert row is not None
    patch_resp = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"time_local": "03:15"},
        headers=headers,
    )
    assert patch_resp.status_code == 200

    # Ensure updated_at differs even under FrozenClock
    row.updated_at = row.updated_at + timedelta(seconds=5)
    db_session.commit()

    r2 = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
    assert r2.status_code == 200
    cid_2 = r2.json()["chart"]["chart_id"]
    assert cid_2 != cid_1

    # Also ensure unused label_enc / place_name_enc tampering (without touching updated_at)
    # does not affect or fail chart calculation.
    db_session.execute(
        text("UPDATE birth_profiles SET label_enc = :lbl, place_name_enc = :plc WHERE id = :pid"),
        {
            "lbl": encrypt_text("Tampered Label", Fernet.generate_key().decode("ascii")),
            "plc": b"corrupt-place",
            "pid": uuid.UUID(pid).hex,
        },
    )
    db_session.commit()
    db_session.expire_all()
    r3 = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
    assert r3.status_code == 200
    assert r3.json()["chart"]["chart_id"] == cid_2
