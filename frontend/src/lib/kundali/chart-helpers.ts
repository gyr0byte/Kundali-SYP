import type {
  AllowlistedLlmPayload,
  BirthProfile,
  ChartCalculationState,
  ChartFactLagna,
  ChartFactPlacement,
  ChartFacts,
  ChartFactSensitivity,
  ChartSettings,
  ProvenanceDisplayStatus,
  SettingsChangeScope,
} from "./types";

export function formatDegreeInSign(degree: number): string {
  const normalized = ((degree % 30) + 30) % 30;
  let wholeDeg = Math.floor(normalized);
  let minutes = Math.round((normalized - wholeDeg) * 60);
  if (minutes === 60) {
    wholeDeg += 1;
    minutes = 0;
  }
  return `${String(wholeDeg).padStart(2, "0")}°${String(minutes).padStart(2, "0")}′`;
}

export function getLagnaFact(chart: ChartFacts | null): ChartFactLagna | null {
  if (!chart) return null;
  const found = chart.facts.find((fact): fact is ChartFactLagna => fact.type === "lagna");
  return found ?? null;
}

export function getPlacementFacts(chart: ChartFacts | null): ChartFactPlacement[] {
  if (!chart) return [];
  return chart.facts.filter((fact): fact is ChartFactPlacement => fact.type === "placement");
}

export function getSensitivityFact(chart: ChartFacts | null): ChartFactSensitivity | null {
  if (!chart) return null;
  const found = chart.facts.find(
    (fact): fact is ChartFactSensitivity => fact.type === "sensitivity"
  );
  return found ?? null;
}

/**
 * Resolves document-level ephemeris provenance strictly from ChartMetadata.
 * Unverified or unavailable calculation states must resolve to "unknown" and
 * never appear as verified ("swieph").
 */
export function getProvenanceStatus(
  chart: ChartFacts | null,
  calcState: ChartCalculationState
): ProvenanceDisplayStatus {
  if (calcState !== "ready" || !chart) {
    return "unknown";
  }
  const src = chart.metadata?.ephemeris_source;
  if (src === "swieph" || src === "moshier") {
    return src;
  }
  return "unknown";
}

/**
 * Determines which computations are invalidated by a staged ChartSettings change.
 * Changing `year_days` affects Dasha period boundaries only and must never trigger
 * Swiss Ephemeris planetary-position recomputation.
 */
export function classifySettingsChange(
  applied: ChartSettings,
  staged: ChartSettings
): SettingsChangeScope {
  const ephemerisChanged =
    applied.ayanamsha !== staged.ayanamsha ||
    applied.node_type !== staged.node_type ||
    applied.preset !== staged.preset;
  if (ephemerisChanged) {
    return "full_chart";
  }
  if (applied.year_days !== staged.year_days) {
    return "dasha_only";
  }
  return "none";
}

/**
 * Returns the 12 zodiac sign indices (0=Aries..11=Pisces) corresponding to Whole Sign
 * Houses 1 through 12 for a given Lagna sign index.
 */
export function getWholeSignHouseMap(lagnaSignIndex: number): number[] {
  return Array.from({ length: 12 }, (_, idx) => (lagnaSignIndex + idx) % 12);
}

export function isUnknownTimeProfile(profile: BirthProfile | null): boolean {
  return profile?.time_certainty === "unknown";
}

/**
 * Projects only allowlisted derived chart facts and convention context for LLM use.
 * Strictly excludes ChartMetadata (datetime_utc_iso, julian_day, utc_offset_hours)
 * and any raw birth input fields.
 */
export function buildAllowlistedLlmPayload(
  chart: ChartFacts,
  selectedFactIds?: string[]
): AllowlistedLlmPayload {
  const allowSet = selectedFactIds ? new Set(selectedFactIds) : null;
  const projectedFacts: AllowlistedLlmPayload["facts"] = [];

  for (const fact of chart.facts) {
    if (allowSet && !allowSet.has(fact.id)) {
      continue;
    }
    if (fact.type === "lagna") {
      projectedFacts.push({
        id: fact.id,
        type: fact.type,
        sign: fact.sign,
        degree: fact.degree,
        nakshatra: fact.nakshatra,
        pada: fact.pada,
      });
    } else if (fact.type === "placement") {
      projectedFacts.push({
        id: fact.id,
        type: fact.type,
        planet: fact.planet,
        sign: fact.sign,
        house: fact.house,
        degree: fact.degree,
        nakshatra: fact.nakshatra,
        pada: fact.pada,
        retrograde: fact.retrograde,
      });
    } else if (fact.type === "sensitivity") {
      projectedFacts.push({
        id: fact.id,
        type: fact.type,
        degree_in_sign: fact.degree_in_sign,
        boundary_distance_degrees: fact.boundary_distance_degrees,
        note: fact.note,
      });
    }
  }

  return {
    facts: projectedFacts,
    conventions: {
      ayanamsha: chart.settings.ayanamsha,
      node_type: chart.settings.node_type,
      house_system: chart.settings.house_system,
      year_days: chart.settings.year_days,
    },
  };
}
