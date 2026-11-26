"""Deterministic calculation engine. Must NEVER import from app.ai."""

from app.calc.ayanamsha import AyanamshaMode, CalculationError, get_ayanamsha_degrees
from app.calc.ephemeris import EphemerisSource, NodeType, calculate_positions
from app.calc.facts import (
    CALCULATION_PRESETS,
    ENGINE_VERSION,
    SUPPORTED_YEAR_DAYS,
    ChartFactLagna,
    ChartFactPlacement,
    ChartFacts,
    ChartMetadata,
    ChartSettings,
    compute_chart_facts,
)
from app.calc.houses import (
    compute_lagna,
    degree_in_sign,
    house_of,
    is_lagna_boundary_sensitive,
    normalize_longitude,
    quantize_longitude,
    sign_name,
    sign_of,
)
from app.calc.nakshatra import nakshatra_of
from app.calc.timeconv import (
    TimeConversionError,
    TimeConversionResult,
    TimeInput,
    convert_local_to_utc_jd,
)

__all__ = [
    "AyanamshaMode",
    "CALCULATION_PRESETS",
    "CalculationError",
    "ChartFactLagna",
    "ChartFactPlacement",
    "ChartFacts",
    "ChartMetadata",
    "ChartSettings",
    "ENGINE_VERSION",
    "EphemerisSource",
    "NodeType",
    "SUPPORTED_YEAR_DAYS",
    "TimeConversionError",
    "TimeConversionResult",
    "TimeInput",
    "calculate_positions",
    "compute_chart_facts",
    "compute_lagna",
    "convert_local_to_utc_jd",
    "degree_in_sign",
    "get_ayanamsha_degrees",
    "house_of",
    "is_lagna_boundary_sensitive",
    "nakshatra_of",
    "normalize_longitude",
    "quantize_longitude",
    "sign_name",
    "sign_of",
]
