"""Integration tests for POST /api/v1/profiles/{profile_id}/chart API contract."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

import app.calc.ayanamsha as ayanamsha_mod
import app.calc.facts as calc_facts_mod
import app.services.chart_service as chart_service_mod
from app.api.schemas.chart import ChartCalculationRequest, ChartCalculationResponse
from app.api.schemas.profile import BirthProfileUpdate
from app.calc.ayanamsha import CalculationError
from app.calc.bikram_sambat import ad_to_bs
from app.calc.ephemeris import EphemerisResult, EphemerisSource, calculate_positions
from app.calc.facts import ENGINE_VERSION, ChartFactSensitivity, compute_chart_facts
from app.calc.timeconv import TimeConversionError
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.permissions import ROLE_PERMISSIONS, Permission, UserRole
from app.core.security import (
    create_access_token,
    encrypt_optional_text,
    encrypt_text,
)
from app.db.models import AstrologerStatus, AuditLog, BirthProfile, ChartSnapshot
from app.geo.nepal import resolve_birthplace
from app.services.profile_service import update_profile


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


@pytest.mark.parametrize("year_days", [360, 365.2425, 365.25])
def test_dasha_uses_saved_settings_and_exact_transition(
    client: TestClient, user_factory: Any, monkeypatch: pytest.MonkeyPatch, year_days: float
) -> None:
    user_factory(email="dasha@example.com")
    headers = _auth_headers(client, "dasha@example.com")
    profile = _create_profile(client, headers, time_certainty="approximate")
    calculated = client.post(
        f"/api/v1/profiles/{profile['id']}/chart",
        json={"year_days": year_days},
        headers=headers,
    )
    assert calculated.status_code == 200
    path = calculated.headers["location"] + "/dasha"

    def unexpected_calculation(*args: object, **kwargs: object) -> None:
        pytest.fail("Dasha must reuse the stored natal chart")

    monkeypatch.setattr("app.services.chart_service.compute_chart_facts", unexpected_calculation)
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["snapshot_id"] == path.split("/")[-2]
    assert data["chart_id"] == calculated.json()["chart"]["chart_id"]
    assert data["year_days"] == year_days
    assert data["is_current_profile_revision"]
    assert data["is_conditional"] and data["time_certainty"] == "approximate"
    assert data["lookup"] == {"as_of": None, "status": "not_requested", "periods": None}
    assert data["facts"][0]["balance"] == data["initial_balance"]
    first, second, *_ = data["mahadashas"]
    transition = first["end_utc_exclusive"]
    assert transition == second["start_utc"]
    moment = datetime.fromisoformat(transition)
    before = client.get(
        path, params={"as_of": (moment - timedelta(microseconds=1)).isoformat()}, headers=headers
    ).json()
    assert before["lookup"]["periods"]["mahadasha"]["period_id"] == first["period_id"]
    at = client.get(path, params={"as_of": transition}, headers=headers)
    assert at.status_code == 200
    assert at.content == client.get(path, params={"as_of": transition}, headers=headers).content
    active = at.json()
    assert active["lookup"]["periods"]["mahadasha"]["period_id"] == second["period_id"]
    assert active["lookup"]["periods"]["pratyantardasha"]["start_utc"] == transition
    assert len(active["facts"]) == 4
    for fact in active["facts"][1:]:
        assert fact["evaluated_at"] == transition
        assert fact["method"] == "vimshottari-v1"
        assert fact["snapshot_id"] == data["snapshot_id"]
    assert len({fact["fact_id"] for fact in active["facts"]}) == 4
    assert active["facts"][1]["fact_id"] != before["facts"][1]["fact_id"]
    for instant, expected in [
        (data["start_utc"], "before_birth"),
        (data["end_utc_exclusive"], "outside_cycle"),
    ]:
        lookup = client.get(path, params={"as_of": instant}, headers=headers).json()
        assert lookup["lookup"]["status"] == expected
        assert lookup["lookup"]["periods"] is None and len(lookup["facts"]) == 1


def test_dasha_snapshot_authorization_revision_and_unknown_time(
    client: TestClient, user_factory: Any
) -> None:
    user_factory(email="dasha-owner@example.com")
    user_factory(email="dasha-other@example.com", role=UserRole.ADMIN)
    owner = _auth_headers(client, "dasha-owner@example.com")
    other = _auth_headers(client, "dasha-other@example.com")
    profile = _create_profile(client, owner, time_certainty="approximate")
    profile_path = f"/api/v1/profiles/{profile['id']}"
    calculated = client.post(profile_path + "/chart", headers=owner)
    path = calculated.headers["location"] + "/dasha"
    initial = client.get(path, headers=owner).json()
    denied = client.get(path, headers=other)
    missing = client.get(f"/api/v1/charts/{uuid.uuid4()}/dasha", headers=owner)
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json()
    unauthenticated = client.get(path)
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["cache-control"] == "no-store"
    for params in (
        {"as_of": "2026-01-01"},
        {"as_of": "2026-01-01T00:00:00.0000001Z"},
        {"as_of": "2026-02-31T00:00:00Z"},
        {"moon_longitude": "10"},
    ):
        invalid = client.get(path, params=params, headers=owner)
        assert invalid.status_code == 422
        assert invalid.headers["cache-control"] == "no-store"
    assert (
        client.patch(
            profile_path,
            json={"time_certainty": "unknown", "time_local": None},
            headers=owner,
        ).status_code
        == 200
    )
    historic = client.get(path, headers=owner).json()
    assert historic == (initial | {"is_current_profile_revision": False})
    lunar = client.post(profile_path + "/chart", headers=owner)
    assert lunar.status_code == 200 and "moon" in lunar.json()
    blocked = client.get(lunar.headers["location"] + "/dasha", headers=owner)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "DASHA_UNKNOWN_BIRTH_TIME"
    assert blocked.headers["cache-control"] == "no-store"
    assert client.delete(profile_path, headers=owner).status_code == 204
    assert client.get(path, headers=owner).status_code == 404


def test_chart_endpoint_success_determinism_settings_and_idempotent_persistence(
    client: TestClient,
    db_session: Session,
    user_factory: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep the calculation body stable and persist only distinct snapshot identities."""
    caplog.set_level(logging.DEBUG)

    user_factory(email="chartowner@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "chartowner@example.com")

    created = _create_profile(client, headers)
    pid = created["id"]
    initial_updated_at = created["updated_at"]

    # Calculations should not append sensitive audit data.
    audit_count_before = db_session.scalar(select(func.count(AuditLog.id))) or 0

    # Each request closes the short persistence transaction, including when it reuses a row.
    orig_commit = db_session.commit
    commit_calls = 0

    def _counting_commit(*args: Any, **kwargs: Any) -> Any:
        nonlocal commit_calls
        commit_calls += 1
        return orig_commit(*args, **kwargs)

    db_session.commit = _counting_commit  # type: ignore[method-assign]
    try:
        # 1. Default calculation with empty JSON {} and completely omitted body match byte-for-byte
        resp_1 = client.post(
            f"/api/v1/profiles/{pid}/chart",
            json={},
            headers=headers | {"Origin": "http://localhost:3000"},
        )
        resp_2 = client.post(f"/api/v1/profiles/{pid}/chart", headers=headers)
        assert resp_1.status_code == 200
        assert resp_2.status_code == 200
        assert resp_1.headers.get("cache-control") == "no-store"
        assert resp_2.headers.get("cache-control") == "no-store"
        assert resp_1.text == resp_2.text
        assert resp_1.headers["location"] == resp_2.headers["location"]
        assert "location" in resp_1.headers["access-control-expose-headers"].lower()

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

        assert commit_calls == 4
        assert db_session.scalar(select(func.count(ChartSnapshot.id))) == 3
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


def test_snapshot_readback_encryption_isolation_and_cascade(
    client: TestClient, db_session: Session, user_factory: Any, test_settings: Settings
) -> None:
    user_factory(email="snapshots@example.com")
    user_factory(email="snapshot-admin@example.com", role=UserRole.ADMIN)
    owner = _auth_headers(client, "snapshots@example.com")
    intruder = _auth_headers(client, "snapshot-admin@example.com")
    first_profile = _create_profile(client, owner)
    second_profile = _create_profile(client, owner)
    other_profile = _create_profile(client, intruder)

    profiles = [(first_profile, owner), (second_profile, owner), (other_profile, intruder)]
    computed = [client.post(f"/api/v1/profiles/{p['id']}/chart", headers=h) for p, h in profiles]
    assert all(response.status_code == 200 for response in computed)
    assert len({response.json()["chart"]["chart_id"] for response in computed}) == 1
    locations = [response.headers["location"] for response in computed]
    assert len(set(locations)) == 3
    location = locations[0]
    snapshot_id = uuid.UUID(location.rsplit("/", 1)[1])
    assert len(set(db_session.scalars(select(ChartSnapshot.fingerprint_key)).all())) == 3

    assert client.get(location).status_code == 401
    assert client.get(location, headers=intruder).status_code == 404
    assert client.get(locations[2], headers=owner).status_code == 404
    fingerprint = computed[0].json()["chart"]["chart_id"]
    assert client.get(f"/api/v1/charts/{fingerprint}", headers=owner).status_code == 422
    snapshot = client.get(location, headers=owner)
    assert snapshot.status_code == 200
    assert snapshot.headers["cache-control"] == "no-store"
    saved = snapshot.json()
    assert saved["chart"] == computed[0].json()["chart"]
    assert saved["schema_version"] == saved["profile_revision"] == 1
    assert saved["is_current_profile_revision"] is True
    assert saved["fact_units"] == {"angle": "degree", "speed": "degree/day"}

    ciphertext = db_session.scalar(
        select(ChartSnapshot.payload_enc).where(ChartSnapshot.id == snapshot_id)
    )
    assert ciphertext is not None and ciphertext.startswith(b"gAAAAA")
    plaintext = Fernet(test_settings.ENCRYPTION_KEY.encode()).decrypt(ciphertext)
    assert b'"facts"' in plaintext
    for unused in (b"Fixture 001 Birth", b"Morang", b"87.283"):
        assert unused not in plaintext
    assert b'"datetime_utc_iso"' not in ciphertext

    # A migrated row cannot be made to serve another snapshot by swapping ciphertext.
    first_row = db_session.get(ChartSnapshot, snapshot_id)
    assert first_row is not None
    other_row = db_session.get(ChartSnapshot, uuid.UUID(locations[2].rsplit("/", 1)[1]))
    assert other_row is not None
    first_row.payload_enc = other_row.payload_enc
    db_session.commit()
    corrupt = client.get(location, headers=owner)
    assert corrupt.status_code == 500
    assert corrupt.json() == {"detail": "Unable to read chart snapshot"}

    assert (
        client.delete(f"/api/v1/profiles/{first_profile['id']}", headers=owner).status_code == 204
    )
    assert client.get(location, headers=owner).status_code == 404
    assert (
        db_session.scalar(select(ChartSnapshot.id).where(ChartSnapshot.id == snapshot_id)) is None
    )
    assert client.get(locations[1], headers=owner).status_code == 200


@pytest.mark.parametrize("operation", ["edit", "delete"])
def test_snapshot_rejects_profile_mutated_during_calculation(
    client: TestClient,
    db_session: Session,
    user_factory: Any,
    test_clock: FrozenClock,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    owner = user_factory()
    owner_id = owner.id
    headers = _auth_headers(client, owner.email)
    created = _create_profile(client, headers)
    profile_id = uuid.UUID(created["id"])

    def mutate_then_compute(*args: Any, **kwargs: Any) -> Any:
        assert not db_session.in_transaction()
        profile = db_session.get(BirthProfile, profile_id)
        assert profile is not None
        if operation == "edit":
            # The frozen clock proves timestamp equality cannot hide a changed revision.
            update_profile(
                db_session,
                profile=profile,
                owner_id=owner_id,
                payload=BirthProfileUpdate(time_local="04:00"),
                clock=test_clock,
                settings=test_settings,
            )
        else:
            db_session.delete(profile)
            db_session.commit()
        return compute_chart_facts(*args, **kwargs)

    monkeypatch.setattr(chart_service_mod, "compute_chart_facts", mutate_then_compute)
    result = client.post(f"/api/v1/profiles/{profile_id}/chart", headers=headers)
    assert result.status_code == 409
    assert result.json()["code"] == "PROFILE_CHANGED"
    assert "location" not in result.headers
    assert db_session.scalar(select(func.count(ChartSnapshot.id))) == 0


def test_snapshot_insert_failure_rolls_back(
    client: TestClient, db_session: Session, user_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = user_factory()
    headers = _auth_headers(client, user.email)
    profile = _create_profile(client, headers)

    def fail_after_flush() -> None:
        db_session.flush()
        raise RuntimeError("private storage details")

    with monkeypatch.context() as patch:
        patch.setattr(db_session, "commit", fail_after_flush)
        response = client.post(f"/api/v1/profiles/{profile['id']}/chart", headers=headers)
    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to compute birth chart"}
    assert "location" not in response.headers
    assert db_session.scalar(select(func.count(ChartSnapshot.id))) == 0
    assert (
        client.post(f"/api/v1/profiles/{profile['id']}/chart", headers=headers).status_code == 200
    )


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
    db_session: Session,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pending BS profiles are blocked and unknown-time profiles bypass the natal engine."""
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
    legacy = db_session.get(BirthProfile, uuid.UUID(bs_profile["id"]))
    assert legacy is not None
    legacy.date_ad_enc = None
    db_session.commit()
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
    assert unk_resp.status_code == 200
    assert unk_resp.headers.get("cache-control") == "no-store"
    assert unk_resp.json()["time_certainty"] == "unknown"
    assert "chart" not in unk_resp.json()


def test_chart_endpoint_sanitized_422_validation_and_synthetic_isolation(
    client: TestClient,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
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
    messages = [r.getMessage() for r in caplog.records if r.name == "app.api.v1.charts"]
    assert messages == ["Chart calculation failed: time_conversion"]
    for sensitive in ("2006-08-02", "02:10", "Asia/Kathmandu", headers["Authorization"]):
        assert sensitive not in caplog.text


def test_chart_request_schema_matches_defaults_and_explicit_null_validation(
    client: TestClient, user_factory: Any
) -> None:
    properties_with_defaults = {
        "ayanamsha": "lahiri",
        "house_system": "whole_sign",
        "node_type": "mean",
        "year_days": 365.25,
    }
    openapi = client.get("/openapi.json").json()
    endpoint = openapi["paths"]["/api/v1/profiles/{profile_id}/chart"]["post"]
    schema_ref = endpoint["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    openapi_schema = openapi["components"]["schemas"][schema_ref.rsplit("/", 1)[-1]]

    for schema in (ChartCalculationRequest.model_json_schema(), openapi_schema):
        assert not (set(properties_with_defaults) & set(schema.get("required", [])))
        for name, default in properties_with_defaults.items():
            field = schema["properties"][name]
            assert field["default"] == default
            assert field.get("type") != "null"
            assert not any(choice.get("type") == "null" for choice in field.get("anyOf", []))
        assert schema["properties"]["year_days"]["enum"] == [360.0, 365.2425, 365.25]

    user_factory(email="chart-schema@example.com")
    headers = _auth_headers(client, "chart-schema@example.com")
    pid = _create_profile(client, headers)["id"]
    url = f"/api/v1/profiles/{pid}/chart"
    default_response = client.post(url, headers=headers)
    assert default_response.status_code == 200
    assert default_response.json()["chart"]["settings"] == {
        **properties_with_defaults,
        "preset": None,
    }
    explicit = client.post(url, json=properties_with_defaults, headers=headers)
    assert explicit.status_code == 200
    assert explicit.json() == default_response.json()

    for name in properties_with_defaults:
        resp = client.post(url, json={name: None}, headers=headers)
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["loc"] == ["body", name]


def test_chart_endpoint_rejects_unsupported_year_days_without_numeric_overflow(
    client: TestClient, user_factory: Any
) -> None:
    user_factory(email="chart-year-days@example.com")
    headers = _auth_headers(client, "chart-year-days@example.com")
    pid = _create_profile(client, headers)["id"]
    url = f"/api/v1/profiles/{pid}/chart"

    for value in (10**400, -(10**400), 361, 365.2426, True, False, "365.25"):
        resp = client.post(url, json={"year_days": value}, headers=headers)
        assert resp.status_code == 422
        detail = resp.json()["detail"][0]
        assert detail["loc"] == ["body", "year_days"]
        assert "input" not in detail

    for value in (360, 360.0, 365.2425, 365.25):
        resp = client.post(url, json={"year_days": value}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["chart"]["settings"]["year_days"] == value


def test_chart_endpoint_uses_native_date_coverage_without_restricting_profile_storage(
    client: TestClient,
    user_factory: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ayanamsha_mod, "EPHE_DIR", tmp_path)
    monkeypatch.delenv("SE_EPHE_PATH", raising=False)
    user_factory(email="chart-date-range@example.com")
    headers = _auth_headers(client, "chart-date-range@example.com")

    for entered_date, time_local in (("0001-01-01", "00:00"), ("3003-04-28", "22:00")):
        pid = _create_profile(
            client, headers, entered_date=entered_date, time_local=time_local, timezone="UTC"
        )["id"]
        resp = client.post(
            f"/api/v1/profiles/{pid}/chart", json={"node_type": "true"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["chart"]["metadata"]["ephemeris_source"] == "moshier"

    for entered_date in ("3003-04-29", "3500-01-01"):
        pid = _create_profile(
            client, headers, entered_date=entered_date, time_local="00:00", timezone="UTC"
        )["id"]
        resp = client.post(f"/api/v1/profiles/{pid}/chart", headers=headers)
        assert resp.status_code == 409
        assert resp.headers["cache-control"] == "no-store"
        assert resp.json()["code"] == "CHART_DATE_OUT_OF_RANGE"
        assert "Check the saved birth date" in resp.json()["detail"]
        assert entered_date not in resp.text


def test_chart_endpoint_decryption_calc_and_unexpected_500_fail_closed(
    client: TestClient,
    db_session: Session,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
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

    records = [record for record in caplog.records if record.name == "app.api.v1.charts"]
    assert [record.getMessage() for record in records] == [
        "Chart calculation failed: native_calculation",
        "Chart calculation failed: unexpected",
        "Chart calculation failed: unexpected",
        "Chart calculation failed: profile_decryption",
    ]
    assert all(record.exc_info is None for record in records)
    for sensitive in (
        "2006-08-02",
        "02:10",
        "Morang",
        "26.45",
        "swe_calc_ut",
        "unexpected traceback",
        "internal secret crash",
        "InvalidToken",
        "gAAAAA",
        wrong_key,
        headers["Authorization"].removeprefix("Bearer "),
    ):
        assert sensitive not in caplog.text


def test_chart_endpoint_handles_mixed_ephemeris_provenance(
    client: TestClient,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API preserves swieph, moshier, and mixed provenance verbatim from calc engine."""
    user_factory(email="prov@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "prov@example.com")
    pid = _create_profile(client, headers)["id"]

    def _make_source_variant(source: EphemerisSource) -> Any:
        def _wrapped(*args: Any, **kwargs: Any) -> EphemerisResult:
            return calculate_positions(*args, **kwargs).model_copy(
                update={"ephemeris_source": source}
            )

        return _wrapped

    for expected_source in ("swieph", "moshier", "mixed"):
        monkeypatch.setattr(
            calc_facts_mod, "calculate_positions", _make_source_variant(expected_source)
        )
        resp = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["chart"]["metadata"]["ephemeris_source"] == expected_source
        saved = client.get(resp.headers["location"], headers=headers)
        assert saved.json()["chart"]["metadata"]["ephemeris_source"] == expected_source


def test_chart_endpoint_profile_edit_updates_chart_id_deterministically(
    client: TestClient,
    db_session: Session,
    user_factory: Any,
    test_clock: FrozenClock,
) -> None:
    """Computation uses the new birth time persisted by the real profile PATCH."""
    user_factory(email="edit_chart@example.com", role=UserRole.USER)
    headers = _auth_headers(client, "edit_chart@example.com")
    created = _create_profile(client, headers)
    pid = created["id"]

    r1 = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
    assert r1.status_code == 200
    first_chart = r1.json()["chart"]
    assert datetime.fromisoformat(first_chart["metadata"]["datetime_utc_iso"]) == datetime(
        2006, 8, 1, 20, 25, tzinfo=UTC
    )

    test_clock.advance(timedelta(seconds=5))
    patch_resp = client.patch(
        f"/api/v1/profiles/{pid}",
        json={"time_local": "03:15"},
        headers=headers,
    )
    assert patch_resp.status_code == 200

    assert patch_resp.json()["updated_at"] != created["updated_at"]
    r2 = client.post(f"/api/v1/profiles/{pid}/chart", json={}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["profile_updated_at"] == patch_resp.json()["updated_at"]
    historic = client.get(r1.headers["location"], headers=headers).json()
    current = client.get(r2.headers["location"], headers=headers).json()
    assert historic["chart"] == first_chart and not historic["is_current_profile_revision"]
    assert current["is_current_profile_revision"] is True
    assert historic["profile_revision"] + 1 == current["profile_revision"]
    edited_chart = r2.json()["chart"]
    assert datetime.fromisoformat(edited_chart["metadata"]["datetime_utc_iso"]) == datetime(
        2006, 8, 1, 21, 30, tzinfo=UTC
    )
    previous_lagna = next(f for f in first_chart["facts"] if f["id"] == "f_lagna")
    edited_lagna = next(f for f in edited_chart["facts"] if f["id"] == "f_lagna")
    assert abs(edited_lagna["longitude"] - previous_lagna["longitude"]) > 1.0
    cid_2 = edited_chart["chart_id"]
    assert cid_2 != first_chart["chart_id"]

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
    assert r3.headers["location"] == r2.headers["location"]


def test_snapshot_identity_preserves_engine_version_and_revision(
    client: TestClient, user_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = user_factory()
    headers = _auth_headers(client, user.email)
    profile = _create_profile(client, headers)
    path = f"/api/v1/profiles/{profile['id']}"
    original = client.post(f"{path}/chart", headers=headers)
    assert original.status_code == 200

    # A metadata-only profile edit starts a new profile revision even if the chart is identical.
    assert client.patch(path, json={"label": "Renamed profile"}, headers=headers).status_code == 200
    renamed = client.post(f"{path}/chart", headers=headers)
    assert renamed.status_code == 200
    assert renamed.json()["chart"] == original.json()["chart"]
    assert renamed.headers["location"] != original.headers["location"]
    historical = client.get(original.headers["location"], headers=headers).json()
    assert historical["is_current_profile_revision"] is False

    monkeypatch.setattr(calc_facts_mod, "ENGINE_VERSION", "0.2.99")
    upgraded = client.post(f"{path}/chart", headers=headers)
    assert upgraded.status_code == 200
    assert upgraded.headers["location"] != renamed.headers["location"]
    assert upgraded.json()["chart"]["engine_version"] == "0.2.99"
    assert upgraded.json()["chart"]["chart_id"] != renamed.json()["chart"]["chart_id"]
    assert (
        client.get(renamed.headers["location"], headers=headers).json()["chart"]
        == renamed.json()["chart"]
    )


def test_equivalent_calendars_legacy_resolution_and_snapshot_history(
    client: TestClient, db_session: Session, user_factory: Any
) -> None:
    user = user_factory()
    headers = _auth_headers(client, user.email)
    ad = _create_profile(client, headers, entered_date="2015-04-25")
    bs = _create_profile(client, headers, input_calendar="BS", entered_date="२०७२-०१-१२")
    assert bs["entered_date"] == "2072-01-12" and bs["date_ad"] == "2015-04-25"
    ad_path = f"/api/v1/profiles/{ad['id']}"
    bs_path = f"/api/v1/profiles/{bs['id']}"
    legacy = db_session.get(BirthProfile, uuid.UUID(bs["id"]))
    assert legacy is not None and legacy.date_ad_enc != b"2015-04-25"
    legacy.date_ad_enc = None
    db_session.commit()
    assert (
        client.get(bs_path, headers=headers).json()["bs_conversion_status"]
        == "awaiting_bs_conversion"
    )
    assert (
        client.post(f"{bs_path}/chart", headers=headers).json()["code"] == "AWAITING_BS_CONVERSION"
    )
    rejected = client.patch(bs_path, json={"entered_date": "2072-01-33"}, headers=headers)
    assert rejected.status_code == 422 and rejected.json()["code"] == "invalid_bs_date"
    assert "2072-01-33" not in rejected.text
    assert client.get(bs_path, headers=headers).json()["date_ad"] is None
    assert (
        client.patch(bs_path, json={"entered_date": "2072-01-12"}, headers=headers).json()[
            "date_ad"
        ]
        == "2015-04-25"
    )

    ad_result = client.post(f"{ad_path}/chart", headers=headers)
    bs_result = client.post(f"{bs_path}/chart", headers=headers)
    assert ad_result.status_code == bs_result.status_code == 200
    assert ad_result.json()["chart"] == bs_result.json()["chart"]
    assert ad_result.headers["location"] != bs_result.headers["location"]
    original = bs_result.headers["location"]
    assert (
        client.patch(bs_path, json={"entered_date": "2072-01-13"}, headers=headers).status_code
        == 200
    )
    old = client.get(original, headers=headers).json()
    assert old["chart"] == bs_result.json()["chart"] and old["is_current_profile_revision"] is False
    new = client.post(f"{bs_path}/chart", headers=headers)
    assert new.status_code == 200 and new.json()["chart"]["chart_id"] != old["chart"]["chart_id"]


def test_birthplace_selection_matches_manual_chart_and_updates_snapshot_revision(
    client: TestClient, user_factory: Any
) -> None:
    user = user_factory()
    headers = _auth_headers(client, user.email)
    kathmandu = resolve_birthplace(1283240)
    assert kathmandu is not None
    manual = _create_profile(
        client,
        headers,
        entered_date="2015-04-25",
        time_local="08:30",
        latitude=kathmandu.latitude,
        longitude=kathmandu.longitude,
    )
    selected = _create_profile(
        client,
        headers,
        input_calendar="BS",
        entered_date="2072-01-12",
        time_local="08:30",
        location_id=kathmandu.id,
        place_name="tampered",
        latitude="tampered",
        longitude=0,
        timezone="America/New_York",
    )
    assert selected["date_ad"] == "2015-04-25"
    assert selected["place_name"] == kathmandu.profile_name
    assert selected["latitude"] == kathmandu.latitude
    assert selected["longitude"] == kathmandu.longitude
    assert selected["timezone"] == "Asia/Kathmandu"

    profile_path = f"/api/v1/profiles/{selected['id']}"
    selected_chart = client.post(f"{profile_path}/chart", headers=headers)
    manual_chart = client.post(f"/api/v1/profiles/{manual['id']}/chart", headers=headers)
    assert selected_chart.status_code == manual_chart.status_code == 200
    assert selected_chart.json()["chart"] == manual_chart.json()["chart"]
    snapshot_url = selected_chart.headers["location"]
    assert snapshot_url != manual_chart.headers["location"]
    original = client.get(snapshot_url, headers=headers).json()
    assert original["is_current_profile_revision"]

    invalid = client.patch(profile_path, json={"location_id": 1}, headers=headers)
    assert invalid.status_code == 422 and invalid.json()["code"] == "invalid_birthplace"
    assert client.get(snapshot_url, headers=headers).json()["is_current_profile_revision"]
    updated = client.patch(
        profile_path,
        json={"location_id": 1282898, "longitude": -90},
        headers=headers,
    )
    assert updated.status_code == 200
    pokhara = resolve_birthplace(1282898)
    assert pokhara is not None and updated.json()["longitude"] == pokhara.longitude
    historic = client.get(snapshot_url, headers=headers).json()
    assert historic["is_current_profile_revision"] is False
    assert historic["chart"] == original["chart"]
    latest = client.post(f"{profile_path}/chart", headers=headers)
    assert latest.status_code == 200
    assert latest.headers["location"] != snapshot_url
    assert latest.json()["chart"]["chart_id"] != historic["chart"]["chart_id"]


def test_search_and_historical_clock_errors_are_bounded_and_sanitized(
    client: TestClient, user_factory: Any
) -> None:
    endpoint = "/api/v1/birthplaces/search"
    assert client.post(endpoint, json={"query": "Kathmandu"}).status_code == 401
    user = user_factory()
    headers = _auth_headers(client, user.email)
    search = client.post(endpoint, json={"query": "काठमाडौं"}, headers=headers)
    assert search.status_code == 200 and search.json()[0]["id"] == 1283240
    assert search.headers["cache-control"] == "no-store"
    long_query = "A" * 81
    rejected = client.post(endpoint, json={"query": long_query}, headers=headers)
    assert rejected.status_code == 422 and long_query not in rejected.text

    bs_date = ad_to_bs(datetime(1986, 1, 1).date()).isoformat()
    payload = {
        "label": "Historical fixture",
        "location_id": 1283240,
        "input_calendar": "BS",
        "entered_date": bs_date,
        "time_certainty": "exact",
        "time_local": "00:10",
    }
    gap = client.post("/api/v1/profiles", json=payload, headers=headers)
    assert gap.status_code == 422 and gap.json()["code"] == "dst_gap"
    assert bs_date not in gap.text and "00:10" not in gap.text
    created = client.post(
        "/api/v1/profiles",
        json={**payload, "time_local": "00:15"},
        headers=headers,
    )
    assert created.status_code == 201 and created.json()["date_ad"] == "1986-01-01"
    updated = client.patch(
        f"/api/v1/profiles/{created.json()['id']}",
        json={"input_calendar": "AD", "entered_date": "1919-12-31", "time_local": "23:50"},
        headers=headers,
    )
    assert updated.status_code == 422 and updated.json()["code"] == "dst_overlap"


def test_unknown_time_snapshot_idempotency_and_known_time_transitions(
    client: TestClient, user_factory: Any
) -> None:
    owner = user_factory()
    headers = _auth_headers(client, owner.email)
    other = _auth_headers(client, user_factory(email="other-lunar-profile@example.com").email)
    ad = _create_profile(
        client,
        headers,
        entered_date="2015-04-25",
        time_certainty="unknown",
        time_local=None,
    )
    bs = _create_profile(
        client,
        headers,
        input_calendar="BS",
        entered_date="2072-01-12",
        time_certainty="unknown",
        time_local=None,
    )
    profile = f"/api/v1/profiles/{ad['id']}"
    first = client.post(f"{profile}/chart", headers=headers)
    again = client.post(f"{profile}/chart", json={"node_type": "true"}, headers=headers)
    equivalent = client.post(f"/api/v1/profiles/{bs['id']}/chart", headers=headers)
    assert first.status_code == again.status_code == equivalent.status_code == 200
    assert first.json()["moon"] == again.json()["moon"] == equivalent.json()["moon"]
    assert "chart" not in first.json()
    assert first.json()["moon"]["chart_id"].startswith("m_")
    snapshot_url = first.headers["location"]
    assert snapshot_url == again.headers["location"] != equivalent.headers["location"]
    snapshot = client.get(snapshot_url, headers=headers).json()
    assert snapshot["schema_version"] == 2 and snapshot["is_current_profile_revision"]
    assert snapshot["moon"] == first.json()["moon"]
    assert "fact_units" not in snapshot and "chart" not in snapshot
    assert client.get(snapshot_url, headers=other).status_code == 404

    known = client.patch(
        profile, json={"time_certainty": "exact", "time_local": "08:30"}, headers=headers
    )
    assert known.status_code == 200
    natal = client.post(f"{profile}/chart", headers=headers)
    assert natal.status_code == 200 and natal.json()["chart"]["chart_id"].startswith("c_")
    assert "moon" not in natal.json()
    natal_url = natal.headers["location"]
    assert client.get(natal_url, headers=headers).json()["schema_version"] == 1
    assert not client.get(snapshot_url, headers=headers).json()["is_current_profile_revision"]
    unknown = client.patch(
        profile, json={"time_certainty": "unknown", "time_local": None}, headers=headers
    )
    assert unknown.status_code == 200
    lunar_again = client.post(f"{profile}/chart", headers=headers)
    assert lunar_again.status_code == 200 and lunar_again.json()["moon"] == snapshot["moon"]
    assert lunar_again.headers["location"] != snapshot_url
    assert not client.get(natal_url, headers=headers).json()["is_current_profile_revision"]


@pytest.mark.parametrize(
    ("day", "timezone", "status_code", "code"),
    [
        ("1800-12-31", "UTC", 409, "CHART_DATE_OUT_OF_RANGE"),
        ("2011-12-30", "Pacific/Apia", 422, "nonexistent_local_date"),
    ],
)
def test_unknown_time_rejects_out_of_scope_or_skipped_local_dates(
    client: TestClient,
    user_factory: Any,
    day: str,
    timezone: str,
    status_code: int,
    code: str,
) -> None:
    headers = _auth_headers(client, user_factory().email)
    profile = _create_profile(
        client,
        headers,
        entered_date=day,
        timezone=timezone,
        time_certainty="unknown",
        time_local=None,
    )
    result = client.post(f"/api/v1/profiles/{profile['id']}/chart", headers=headers)
    assert result.status_code == status_code and result.json()["code"] == code
    assert result.headers.get("location") is None and day not in result.text
