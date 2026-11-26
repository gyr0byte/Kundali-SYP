"""Unit tests for chart schemas, minimal profile decryption, chart service, and audit defense."""

from __future__ import annotations

import datetime
import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

import app.services.chart_service as chart_service_mod
from app.api.schemas.chart import ChartCalculationRequest, ChartCalculationResponse
from app.calc.ayanamsha import AyanamshaMode, CalculationError
from app.calc.ephemeris import EphemerisSource, NodeType
from app.calc.facts import (
    ENGINE_VERSION,
    ChartFactLagna,
    ChartFactPlacement,
    ChartFacts,
    ChartMetadata,
    ChartSettings,
)
from app.calc.timeconv import TimeConversionError, TimeInput
from app.core.config import Settings
from app.core.security import (
    encrypt_float,
    encrypt_optional_text,
    encrypt_text,
)
from app.db.models.profile import BirthProfile, InputCalendar, TimeCertainty
from app.services.audit_service import sanitize_metadata
from app.services.chart_service import (
    ChartCalculationFailureError,
    ChartProfileConflictError,
    ChartTimeInputError,
    build_deterministic_chart_id,
    calculate_profile_chart,
)
from app.services.profile_service import (
    ProfileStorageError,
    decrypt_profile_calc_inputs,
)
from tests.conftest import TEST_ENCRYPTION_KEY


def _make_profile(
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
    updated_at: datetime.datetime | None = None,
) -> BirthProfile:
    """Build an in-memory BirthProfile ORM entity with Fernet-encrypted fields."""
    now = updated_at or datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.UTC)
    return BirthProfile(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
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
        created_at=now,
        updated_at=now,
    )


def test_chart_calculation_request_defaults_presets_and_strict_validation() -> None:
    """Request schema validates year_days, presets, explicit nulls, and rejects client overrides."""
    # Empty request resolves standard defaults
    default_settings = ChartCalculationRequest().to_chart_settings()
    assert default_settings == ChartSettings(
        ayanamsha=AyanamshaMode.LAHIRI,
        house_system="whole_sign",
        node_type=NodeType.MEAN,
        year_days=365.25,
        preset=None,
    )

    # Preset expansion allows explicit year_days override (integer 360 -> 360.0)
    hamro = ChartCalculationRequest.model_validate(
        {"preset": "hamro_patro_compat", "year_days": 360}
    ).to_chart_settings()
    assert hamro == ChartSettings(
        ayanamsha=AyanamshaMode.LAHIRI_1940,
        house_system="whole_sign",
        node_type=NodeType.TRUE,
        year_days=360.0,
        preset="hamro_patro_compat",
    )

    # All supported year_days literals normalize cleanly
    for raw_val, expected_float in ((360, 360.0), (365.2425, 365.2425), (365.25, 365.25)):
        cfg = ChartCalculationRequest.model_validate({"year_days": raw_val}).to_chart_settings()
        assert cfg.year_days == expected_float

    # Rejects client-supplied birth inputs, unknown presets, unsupported year_days, nulls, conflicts
    invalid_payloads: list[dict[str, Any]] = [
        {"date": "1998-07-31"},
        {"time_local": "08:30"},
        {"latitude": 27.7172},
        {"longitude": 85.3240},
        {"timezone": "Asia/Kathmandu"},
        {"chart_id": "c_forged"},
        {"preset": "unknown_preset"},
        {"preset": 123},
        {"preset": "hamro_patro_compat", "ayanamsha": "lahiri"},
        {"preset": "hamro_patro_compat", "node_type": "mean"},
        {"ayanamsha": "tropical"},
        {"house_system": "placidus"},
        {"node_type": "oscillating"},
        {"year_days": 366.0},
        {"year_days": 0},
        {"year_days": -365.25},
        {"year_days": float("nan")},
        {"year_days": True},
        {"year_days": "365.25"},
        {"ayanamsha": None},
        {"house_system": None},
        {"node_type": None},
        {"year_days": None},
    ]
    for bad in invalid_payloads:
        with pytest.raises(ValidationError):
            ChartCalculationRequest.model_validate(bad)


def test_decrypt_profile_calc_inputs_minimality_and_ownership(test_settings: Settings) -> None:
    """Minimal decryption helper reads only calc fields and enforces ownership & integrity."""
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    profile = _make_profile(owner_id=owner_id, label="Secret Owner", place_name="Secret Village")

    # Even if non-calculation fields have invalid/unreadable ciphertext, calc decryption succeeds.
    profile.label_enc = b"not-valid-fernet-at-all"
    profile.entered_date_enc = b"not-valid-fernet-at-all"
    profile.place_name_enc = b"not-valid-fernet-at-all"

    calc_inputs = decrypt_profile_calc_inputs(profile, owner_id=owner_id, settings=test_settings)
    assert calc_inputs.profile_id == profile.id
    assert calc_inputs.date_ad == "1998-07-31"
    assert calc_inputs.time_local == "08:30"
    assert calc_inputs.latitude == 27.7172
    assert calc_inputs.longitude == 85.3240
    assert calc_inputs.timezone == "Asia/Kathmandu"

    with pytest.raises(PermissionError):
        decrypt_profile_calc_inputs(profile, owner_id=other_id, settings=test_settings)

    # Corrupting a calculation-required ciphertext raises ProfileStorageError
    wrong_key = Fernet.generate_key().decode("ascii")
    profile.latitude_enc = encrypt_float(10.0, wrong_key)
    with pytest.raises(ProfileStorageError):
        decrypt_profile_calc_inputs(profile, owner_id=owner_id, settings=test_settings)


def test_deterministic_chart_id_includes_engine_version_and_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """chart_id stays deterministic yet changes with ENGINE_VERSION, updated_at, and settings."""
    pid = uuid.UUID("11111111-1111-1111-1111-111111111111")
    ts1 = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.UTC)
    ts1_naive = datetime.datetime(2026, 1, 1, 12, 0)
    ts2 = datetime.datetime(2026, 1, 1, 12, 1, tzinfo=datetime.UTC)

    base = ChartSettings()
    id_a = build_deterministic_chart_id(profile_id=pid, profile_updated_at=ts1, settings=base)
    id_a_naive = build_deterministic_chart_id(
        profile_id=pid, profile_updated_at=ts1_naive, settings=base
    )
    assert id_a.startswith("c_") and len(id_a) == 18
    assert id_a == id_a_naive

    assert (
        build_deterministic_chart_id(
            profile_id=pid,
            profile_updated_at=ts1,
            settings=base,
            engine_version="9.9.9",
        )
        != id_a
    )
    assert (
        build_deterministic_chart_id(profile_id=pid, profile_updated_at=ts2, settings=base) != id_a
    )
    assert (
        build_deterministic_chart_id(
            profile_id=pid,
            profile_updated_at=ts1,
            settings=ChartSettings(year_days=360.0),
        )
        != id_a
    )
    assert (
        build_deterministic_chart_id(
            profile_id=pid,
            profile_updated_at=ts1,
            settings=ChartSettings(ayanamsha=AyanamshaMode.RAMAN),
        )
        != id_a
    )

    # Confirm engine version bump via module attribute propagates to service chart_id
    monkeypatch.setattr(chart_service_mod, "ENGINE_VERSION", "0.2.99")
    owner = uuid.uuid4()
    profile = _make_profile(owner_id=owner, updated_at=ts1)
    settings_obj = Settings(
        ENVIRONMENT="test",
        JWT_SECRET="x" * 32,
        DATABASE_URL="sqlite:///:memory:",
        ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
    )
    res_bumped = calculate_profile_chart(
        profile, owner_id=owner, calc_settings=base, app_settings=settings_obj
    )
    assert res_bumped.chart.chart_id != id_a
    assert res_bumped.chart.engine_version == ENGINE_VERSION


def test_service_blocks_bs_unknown_and_incomplete_profiles_without_calc(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BS, unknown-time, and incomplete AD profiles raise 409 conflicts without calling calc."""
    calc_calls = 0

    def _forbidden_calc(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal calc_calls
        calc_calls += 1
        raise AssertionError("compute_chart_facts must not be called")

    monkeypatch.setattr(chart_service_mod, "compute_chart_facts", _forbidden_calc)
    owner = uuid.uuid4()

    bs_profile = _make_profile(
        owner_id=owner,
        input_calendar=InputCalendar.BS,
        entered_date="2055-04-15",
        date_ad=None,
    )
    with pytest.raises(ChartProfileConflictError) as bs_exc:
        calculate_profile_chart(
            bs_profile,
            owner_id=owner,
            calc_settings=ChartSettings(),
            app_settings=test_settings,
        )
    assert bs_exc.value.code == "AWAITING_BS_CONVERSION"

    unknown_profile = _make_profile(
        owner_id=owner,
        time_certainty=TimeCertainty.UNKNOWN,
        time_local=None,
    )
    with pytest.raises(ChartProfileConflictError) as unk_exc:
        calculate_profile_chart(
            unknown_profile,
            owner_id=owner,
            calc_settings=ChartSettings(),
            app_settings=test_settings,
        )
    assert unk_exc.value.code == "UNKNOWN_TIME_UNSUPPORTED"

    # Simulated incomplete decrypted profile (e.g. blank timezone or missing time_local in memory)
    incomplete_calc_inputs = SimpleNamespace(
        profile_id=uuid.uuid4(),
        updated_at=datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.UTC),
        input_calendar=InputCalendar.AD,
        time_certainty=TimeCertainty.EXACT,
        date_ad=None,
        time_local="08:30",
        latitude=27.7172,
        longitude=85.3240,
        timezone="Asia/Kathmandu",
    )
    monkeypatch.setattr(
        chart_service_mod, "decrypt_profile_calc_inputs", lambda *_a, **_kw: incomplete_calc_inputs
    )
    ad_stub = _make_profile(owner_id=owner)
    with pytest.raises(ChartProfileConflictError) as inc_exc:
        calculate_profile_chart(
            ad_stub,
            owner_id=owner,
            calc_settings=ChartSettings(),
            app_settings=test_settings,
        )
    assert inc_exc.value.code == "INCOMPLETE_BIRTH_DATA"
    assert calc_calls == 0


def test_service_maps_time_conversion_vs_engine_vs_unexpected_failures(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TimeConversionError -> sanitized 422; CalculationError & unexpected errors -> opaque 500."""
    owner = uuid.uuid4()
    profile = _make_profile(owner_id=owner)

    # 1. Known TimeConversionError -> ChartTimeInputError without raw date/time/timezone echoed
    def _raise_dst_gap(*_args: Any, **_kwargs: Any) -> Any:
        raise TimeConversionError(
            "Nonexistent local time in DST gap: 1998-07-31 08:30 in Asia/Kathmandu",
            code="dst_gap",
        )

    monkeypatch.setattr(chart_service_mod, "compute_chart_facts", _raise_dst_gap)
    with pytest.raises(ChartTimeInputError) as dst_exc:
        calculate_profile_chart(
            profile, owner_id=owner, calc_settings=ChartSettings(), app_settings=test_settings
        )
    assert dst_exc.value.code == "dst_gap"
    assert "1998-07-31" not in dst_exc.value.detail
    assert "08:30" not in dst_exc.value.detail
    assert "Asia/Kathmandu" not in dst_exc.value.detail

    # 2. CalculationError -> ChartCalculationFailureError (opaque, not converted to 422)
    def _raise_calc_err(*_args: Any, **_kwargs: Any) -> Any:
        raise CalculationError("Swiss Ephemeris calculation failed with status=-1")

    monkeypatch.setattr(chart_service_mod, "compute_chart_facts", _raise_calc_err)
    with pytest.raises(ChartCalculationFailureError) as calc_exc:
        calculate_profile_chart(
            profile, owner_id=owner, calc_settings=ChartSettings(), app_settings=test_settings
        )
    assert "status=-1" not in str(calc_exc.value)

    # 3. Unexpected plain ValueError -> ChartCalculationFailureError (NOT blanket-mapped to 422!)
    def _raise_unexpected_value_err(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("unexpected secret math bug 1998-07-31")

    monkeypatch.setattr(chart_service_mod, "compute_chart_facts", _raise_unexpected_value_err)
    with pytest.raises(ChartCalculationFailureError) as val_exc:
        calculate_profile_chart(
            profile, owner_id=owner, calc_settings=ChartSettings(), app_settings=test_settings
        )
    assert "1998-07-31" not in str(val_exc.value)


@pytest.mark.parametrize("source", ["swieph", "moshier", "mixed"])
def test_service_preserves_provenance_and_approximate_certainty(
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    source: EphemerisSource,
) -> None:
    """Service preserves ephemeris provenance and approximate time certainty faithfully."""
    owner = uuid.uuid4()
    profile = _make_profile(owner_id=owner, time_certainty=TimeCertainty.APPROXIMATE)

    def _fake_facts(birth_input: TimeInput, settings: ChartSettings, chart_id: str) -> ChartFacts:
        assert birth_input.timezone == "Asia/Kathmandu"
        return ChartFacts(
            chart_id=chart_id,
            engine_version=ENGINE_VERSION,
            settings=settings,
            metadata=ChartMetadata(
                ephemeris_source=source,
                julian_day=2451025.614583,
                utc_offset_hours=5.75,
                datetime_utc_iso="1998-07-31T02:45:00+00:00",
            ),
            facts=[
                ChartFactLagna(
                    sign="Leo",
                    sign_index=4,
                    degree=15.0,
                    longitude=135.0,
                    nakshatra="Purva Phalguni",
                    pada=1,
                ),
                ChartFactPlacement(
                    id="f_sun",
                    planet="Sun",
                    sign="Cancer",
                    sign_index=3,
                    degree=14.0,
                    longitude=104.0,
                    house=12,
                    nakshatra="Pushya",
                    pada=4,
                    retrograde=False,
                    speed=0.95,
                ),
            ],
        )

    monkeypatch.setattr(chart_service_mod, "compute_chart_facts", _fake_facts)
    res = calculate_profile_chart(
        profile,
        owner_id=owner,
        calc_settings=ChartSettings(),
        app_settings=test_settings,
    )
    assert isinstance(res, ChartCalculationResponse)
    assert res.time_certainty == TimeCertainty.APPROXIMATE
    assert res.chart.metadata.ephemeris_source == source


def test_audit_sanitizer_blocks_chart_derived_birth_metadata_keys() -> None:
    """Audit defense-in-depth strips Julian Day, UTC timestamp, offset, and chart placement keys."""
    dirty = {
        "julian_day": 2451025.614583,
        "datetime_utc_iso": "1998-07-31T02:45:00+00:00",
        "utc_offset_hours": 5.75,
        "time_utc": "02:45:00",
        "lagna_longitude": 135.0,
        "planet_positions": {"sun": 104.0},
        "chart_facts": [{"id": "f_lagna"}],
        "jd": 2451025.614583,
        "nested": {
            "julian_day": 2451025.614583,
            "datetime_utc": "1998-07-31T02:45:00Z",
            "safe_count": 3,
        },
        "engine_version": ENGINE_VERSION,
    }
    cleaned = sanitize_metadata(dirty)
    serialized = json.dumps(cleaned)
    for sensitive in ("2451025", "1998-07-31", "5.75", "02:45", "135.0", "104.0", "f_lagna"):
        assert sensitive not in serialized
    assert cleaned == {
        "nested": {"safe_count": 3},
        "engine_version": ENGINE_VERSION,
    }
