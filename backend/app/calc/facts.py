"""Chart Facts — The contract between the deterministic engine and interpretation layer.

Implements Pydantic v2 models for validated, pure, deterministic Chart Facts per
Kundali_Project_Plan.md §8.9. This module NEVER imports from app.ai.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.calc.ayanamsha import SWE_LOCK, AyanamshaMode, CalculationError
from app.calc.ephemeris import BodyEphemerisSource, EphemerisSource, NodeType, calculate_positions
from app.calc.houses import (
    compute_lagna,
    degree_in_sign,
    house_of,
    is_lagna_boundary_sensitive,
    quantize_longitude,
    sign_name,
    sign_of,
)
from app.calc.nakshatra import nakshatra_of
from app.calc.timeconv import TimeInput, convert_local_to_utc_jd

ENGINE_VERSION: str = "0.2.0"

SUPPORTED_YEAR_DAYS: tuple[float, ...] = (360.0, 365.2425, 365.25)

CALCULATION_PRESETS: dict[str, dict[str, Any]] = {
    "hamro_patro_compat": {
        "ayanamsha": AyanamshaMode.LAHIRI_1940,
        "house_system": "whole_sign",
        "node_type": NodeType.TRUE,
        "year_days": 365.25,
        "preset": "hamro_patro_compat",
    },
}


class ChartSettings(BaseModel):
    """Astronomical calculation conventions."""

    model_config = ConfigDict(extra="forbid")

    ayanamsha: AyanamshaMode = AyanamshaMode.LAHIRI
    house_system: Literal["whole_sign"] = "whole_sign"
    node_type: NodeType = NodeType.MEAN
    year_days: float = Field(default=365.25, description="Year length for Dasha cycles")
    preset: str | None = Field(default=None, description="Optional named calculation preset")

    @field_validator("year_days")
    @classmethod
    def check_year_days_supported(cls, v: float) -> float:
        """Restrict year_days strictly to supported finite Dasha conventions."""
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("year_days must be a valid number")
        numeric = float(v)
        if not math.isfinite(numeric) or numeric not in SUPPORTED_YEAR_DAYS:
            allowed = ", ".join(str(x) for x in SUPPORTED_YEAR_DAYS)
            raise ValueError(f"year_days must be one of {allowed}")
        return numeric

    @field_validator("preset")
    @classmethod
    def check_preset_known(cls, v: str | None) -> str | None:
        """Reject unknown calculation presets rather than ignoring them silently."""
        if v is None:
            return None
        cleaned = v.strip()
        if cleaned not in CALCULATION_PRESETS:
            available = ", ".join(repr(k) for k in CALCULATION_PRESETS)
            raise ValueError(f"Unknown preset {v!r}. Available presets: {available}")
        return cleaned

    @model_validator(mode="after")
    def validate_and_apply_preset_consistency(self) -> ChartSettings:
        """Apply omitted preset defaults or reject explicit fields contradicting preset."""
        if self.preset is None:
            return self
        expected = CALCULATION_PRESETS[self.preset]
        fields_set = self.model_fields_set

        for field_name in ("ayanamsha", "house_system", "node_type"):
            expected_val = expected[field_name]
            current_val = getattr(self, field_name)
            if field_name in fields_set and current_val != expected_val:
                raise ValueError(
                    f"Setting {field_name}={current_val!r} contradicts preset {self.preset!r}"
                )
            if field_name not in fields_set:
                object.__setattr__(self, field_name, expected_val)

        return self

    @classmethod
    def from_preset(cls, preset_name: str) -> ChartSettings:
        """Create ChartSettings from a named preset.

        Available presets:
        - 'hamro_patro_compat': node_type=TRUE, ayanamsha=LAHIRI_1940, house_system=whole_sign
        """
        if preset_name not in CALCULATION_PRESETS:
            available = ", ".join(repr(k) for k in CALCULATION_PRESETS)
            raise ValueError(f"Unknown preset {preset_name!r}. Available presets: {available}")
        return cls(**CALCULATION_PRESETS[preset_name])


class ChartMetadata(BaseModel):
    """Execution metadata and provenance."""

    model_config = ConfigDict(extra="forbid")

    ephemeris_source: EphemerisSource = Field(
        description="'swieph' (high precision), 'moshier' (fallback), or 'mixed' (partial fallback)"
    )
    julian_day: float
    utc_offset_hours: float
    datetime_utc_iso: str


class ChartFactLagna(BaseModel):
    """Fact representing the Ascendant / Lagna."""

    model_config = ConfigDict(extra="forbid")

    id: Literal["f_lagna"] = "f_lagna"
    type: Literal["lagna"] = "lagna"
    sign: str
    sign_index: int
    degree: float
    longitude: float
    nakshatra: str
    pada: int


class ChartFactPlacement(BaseModel):
    """Fact representing a planetary placement in sign and house."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["placement"] = "placement"
    planet: str
    sign: str
    sign_index: int
    degree: float
    longitude: float
    house: int
    nakshatra: str
    pada: int
    retrograde: bool
    speed: float


class ChartFactSensitivity(BaseModel):
    """Fact emitted when Lagna is within 0.5° of a sign boundary."""

    model_config = ConfigDict(extra="forbid")

    id: Literal["f_lagna_sensitivity"] = "f_lagna_sensitivity"
    type: Literal["sensitivity"] = "sensitivity"
    threshold_degrees: float
    degree_in_sign: float
    boundary_distance_degrees: float
    note: str


ChartFact = ChartFactLagna | ChartFactPlacement | ChartFactSensitivity


class ChartFacts(BaseModel):
    """Complete, immutable chart facts document for a single nativity."""

    model_config = ConfigDict(extra="forbid")

    chart_id: str = Field(min_length=1)
    engine_version: str
    settings: ChartSettings
    metadata: ChartMetadata
    facts: list[ChartFact]


_PLANET_NAMES_DISPLAY = [
    ("sun", "Sun"),
    ("moon", "Moon"),
    ("mars", "Mars"),
    ("mercury", "Mercury"),
    ("jupiter", "Jupiter"),
    ("venus", "Venus"),
    ("saturn", "Saturn"),
    ("rahu", "Rahu"),
    ("ketu", "Ketu"),
]


def _quantized_body_geometry(raw_longitude: float) -> tuple[float, int, str, float, str, int]:
    """Quantize longitude first so sign, degree, nakshatra, and pada are always consistent."""
    q_lon = quantize_longitude(raw_longitude, decimals=6)
    s_idx = sign_of(q_lon)
    s_name = sign_name(s_idx)
    deg = round(degree_in_sign(q_lon), 6)
    if deg >= 30.0 or deg == 0.0:
        deg = 0.0
    _, nak_name, pada = nakshatra_of(q_lon)
    return q_lon, s_idx, s_name, deg, nak_name, pada


def _build_result_chart_id(
    *,
    settings: ChartSettings,
    metadata: ChartMetadata,
    facts: list[ChartFact],
    latitude: float,
    longitude: float,
    body_sources: dict[str, BodyEphemerisSource],
) -> str:
    """Hash effective calculation inputs, final chart facts, and native body provenance."""
    payload = {
        "identity_version": 1,
        "engine_version": ENGINE_VERSION,
        "settings": settings.model_dump(mode="json"),
        "metadata": metadata.model_dump(mode="json"),
        "facts": [fact.model_dump(mode="json") for fact in facts],
        "latitude": latitude,
        "longitude": longitude,
        "body_sources": body_sources,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return f"c_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]}"


def compute_chart_facts(
    birth_input: TimeInput,
    settings: ChartSettings,
    chart_id: str | None = None,
) -> ChartFacts:
    """Compute pure, deterministic Chart Facts for a birth input and settings.

    Identical inputs produce byte-identical JSON. Does not use current time.
    When no explicit identifier is supplied, derive one from the calculated result.
    Holds SWE_LOCK across the complete calculation pipeline so shared C library
    state stays atomic across Lagna and planetary evaluations.
    """
    if chart_id is not None and (not isinstance(chart_id, str) or not chart_id.strip()):
        raise ValueError("chart_id must be a non-empty string.")

    with SWE_LOCK:
        time_ctx = convert_local_to_utc_jd(birth_input)
        jd = time_ctx.julian_day
        raw_lagna_lon = compute_lagna(jd, time_ctx.latitude, time_ctx.longitude, settings.ayanamsha)
        eph_res = calculate_positions(
            jd, ayanamsha=settings.ayanamsha, node_type=settings.node_type
        )

    # 1. Quantized Lagna and derived fields
    lagna_lon, lagna_sign_idx, lagna_sign_name, lagna_deg, lagna_nak_name, lagna_pada = (
        _quantized_body_geometry(raw_lagna_lon)
    )

    lagna_fact = ChartFactLagna(
        sign=lagna_sign_name,
        sign_index=lagna_sign_idx,
        degree=lagna_deg,
        longitude=lagna_lon,
        nakshatra=lagna_nak_name,
        pada=lagna_pada,
    )

    # 2. Quantized Planetary Placements referencing quantized Lagna
    facts_list: list[ChartFact] = [lagna_fact]

    for key, display_name in _PLANET_NAMES_DISPLAY:
        pos = eph_res.positions[key]
        if not math.isfinite(pos.speed):
            raise CalculationError(f"Non-finite speed produced for planet {key}.")

        p_lon, p_sign_idx, p_sign_name, p_deg, p_nak_name, p_pada = _quantized_body_geometry(
            pos.longitude
        )
        p_house = house_of(p_lon, lagna_lon)

        facts_list.append(
            ChartFactPlacement(
                id=f"f_{key}",
                planet=display_name,
                sign=p_sign_name,
                sign_index=p_sign_idx,
                degree=p_deg,
                longitude=p_lon,
                house=p_house,
                nakshatra=p_nak_name,
                pada=p_pada,
                retrograde=pos.retrograde,
                speed=round(pos.speed, 6),
            )
        )

    # 3. Check Lagna boundary sensitivity against quantized Lagna longitude
    if is_lagna_boundary_sensitive(lagna_lon, threshold_degrees=0.5):
        dist = round(min(lagna_deg, 30.0 - lagna_deg), 6)
        facts_list.append(
            ChartFactSensitivity(
                threshold_degrees=0.5,
                degree_in_sign=lagna_deg,
                boundary_distance_degrees=dist,
                note=(
                    "Lagna is within 0.5 degrees of a sign boundary; a minor change in "
                    "birth time may alter the rising sign."
                ),
            )
        )

    meta = ChartMetadata(
        ephemeris_source=eph_res.ephemeris_source,
        julian_day=jd,
        utc_offset_hours=time_ctx.utc_offset_hours,
        datetime_utc_iso=time_ctx.datetime_utc.isoformat(),
    )

    if chart_id is None:
        chart_id = _build_result_chart_id(
            settings=settings,
            metadata=meta,
            facts=facts_list,
            latitude=time_ctx.latitude,
            longitude=time_ctx.longitude,
            body_sources=eph_res.body_sources,
        )
    return ChartFacts(
        chart_id=chart_id.strip(),
        engine_version=ENGINE_VERSION,
        settings=settings,
        metadata=meta,
        facts=facts_list,
    )
