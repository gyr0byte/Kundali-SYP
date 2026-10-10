"""Chart Facts — The contract between the deterministic engine and interpretation layer.

Implements Pydantic v2 models for validated, pure, deterministic Chart Facts per
Kundali_Project_Plan.md §8.9. This module NEVER imports from app.ai.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.calc.ayanamsha import AyanamshaMode
from app.calc.ephemeris import NodeType, calculate_positions
from app.calc.houses import (
    compute_lagna,
    degree_in_sign,
    house_of,
    is_lagna_boundary_sensitive,
    sign_name,
    sign_of,
)
from app.calc.nakshatra import nakshatra_of
from app.calc.timeconv import TimeInput, convert_local_to_utc_jd

ENGINE_VERSION: str = "0.1.0"


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

    ephemeris_source: str = Field(description="'swieph' (high precision) or 'moshier' (fallback)")
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


class ChartFacts(BaseModel):
    """Complete, immutable chart facts document for a single nativity."""

    model_config = ConfigDict(extra="forbid")

    chart_id: str
    engine_version: str
    settings: ChartSettings
    metadata: ChartMetadata
    facts: list[ChartFactLagna | ChartFactPlacement | ChartFactSensitivity]


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


def compute_chart_facts(
    birth_input: TimeInput,
    settings: ChartSettings,
    chart_id: str,
) -> ChartFacts:
    """Compute pure, deterministic Chart Facts for a birth input and settings.

    Identical inputs produce byte-identical JSON. Does not use current time.
    """
    time_ctx = convert_local_to_utc_jd(birth_input)
    jd = time_ctx.julian_day

    # 1. Compute Lagna
    lagna_lon = compute_lagna(jd, time_ctx.latitude, time_ctx.longitude, settings.ayanamsha)
    lagna_sign_idx = sign_of(lagna_lon)
    lagna_sign_name = sign_name(lagna_sign_idx)
    lagna_deg = degree_in_sign(lagna_lon)
    _, lagna_nak_name, lagna_pada = nakshatra_of(lagna_lon)

    lagna_fact = ChartFactLagna(
        sign=lagna_sign_name,
        sign_index=lagna_sign_idx,
        degree=round(lagna_deg, 6),
        longitude=round(lagna_lon, 6),
        nakshatra=lagna_nak_name,
        pada=lagna_pada,
    )

    # 2. Compute Planetary Positions
    eph_res = calculate_positions(jd, ayanamsha=settings.ayanamsha, node_type=settings.node_type)

    facts_list: list[ChartFactLagna | ChartFactPlacement | ChartFactSensitivity] = [lagna_fact]

    for key, display_name in _PLANET_NAMES_DISPLAY:
        pos = eph_res.positions[key]
        p_sign_idx = sign_of(pos.longitude)
        p_sign_name = sign_name(p_sign_idx)
        p_deg = degree_in_sign(pos.longitude)
        p_house = house_of(pos.longitude, lagna_lon)
        _, p_nak_name, p_pada = nakshatra_of(pos.longitude)

        facts_list.append(
            ChartFactPlacement(
                id=f"f_{key}",
                planet=display_name,
                sign=p_sign_name,
                sign_index=p_sign_idx,
                degree=round(p_deg, 6),
                longitude=round(pos.longitude, 6),
                house=p_house,
                nakshatra=p_nak_name,
                pada=p_pada,
                retrograde=pos.retrograde,
                speed=round(pos.speed, 6),
            )
        )

    # 3. Check Lagna boundary sensitivity
    if is_lagna_boundary_sensitive(lagna_lon, threshold_degrees=0.5):
        dist = min(lagna_deg, 30.0 - lagna_deg)
        facts_list.append(
            ChartFactSensitivity(
                threshold_degrees=0.5,
                degree_in_sign=round(lagna_deg, 6),
                boundary_distance_degrees=round(dist, 6),
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

    return ChartFacts(
        chart_id=chart_id,
        engine_version=ENGINE_VERSION,
        settings=settings,
        metadata=meta,
        facts=facts_list,
    )
