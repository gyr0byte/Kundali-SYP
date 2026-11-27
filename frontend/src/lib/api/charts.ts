import type { BirthProfile, ChartCalculationResponse, ChartSettings } from "../kundali/types.ts";
import { ApiClientError, apiRequest, type ApiClientConfig } from "./client.ts";

export function calculateChart(
  config: ApiClientConfig,
  profile: BirthProfile,
  settings: ChartSettings,
  signal?: AbortSignal,
  onSnapshot?: (snapshotId: string | null) => void,
): Promise<ChartCalculationResponse> {
  if (profile.is_synthetic_sample || profile.id === "sample_north_london" || !profile.updated_at) {
    throw new ApiClientError({
      code: "VALIDATION_ERROR",
      status: 422,
      message: "Chart calculation requires a persisted birth profile.",
    });
  }

  const body = profile.time_certainty === "unknown" ? { ayanamsha: settings.ayanamsha } : settings.preset
    ? { preset: settings.preset, year_days: settings.year_days }
    : {
        ayanamsha: settings.ayanamsha,
        node_type: settings.node_type,
        house_system: settings.house_system,
        year_days: settings.year_days,
      };

  return apiRequest<ChartCalculationResponse>(`/profiles/${encodeURIComponent(profile.id)}/chart`, {
    method: "POST",
    body,
    config,
    signal,
    onHeaders: onSnapshot
      ? (headers) => onSnapshot(snapshotIdFromLocation(headers.get("Location")))
      : undefined,
  });
}

function snapshotIdFromLocation(location: string | null): string | null {
  const pattern = /^\/api\/v1\/charts\/([\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12})$/i;
  return pattern.exec(location ?? "")?.[1]?.toLowerCase() ?? null;
}

export function matchesChartProfile(result: ChartCalculationResponse, profile: BirthProfile): boolean {
  return result?.profile_id === profile.id &&
    result.profile_updated_at === profile.updated_at &&
    result.input_calendar === profile.input_calendar &&
    result.time_certainty === profile.time_certainty;
}

export type ChartIssue =
  | "bsPending" | "unknownTime" | "incomplete" | "dateRange"
  | "auth" | "forbidden" | "missing" | "validation" | "server" | "network" | "profileChanged"
  | "nonexistentDate";

export function getChartIssue(error: unknown): ChartIssue {
  if (!(error instanceof ApiClientError)) return "server";
  if (error.status === 409) {
    switch (error.responseCode) {
      case "AWAITING_BS_CONVERSION": return "bsPending";
      case "UNKNOWN_TIME_UNSUPPORTED": return "unknownTime";
      case "INCOMPLETE_BIRTH_DATA": return "incomplete";
      case "CHART_DATE_OUT_OF_RANGE": return "dateRange";
    }
  }
  switch (error.status) {
    case 401: return "auth";
    case 403: return "forbidden";
    case 404: return "missing";
    case 422: return error.responseCode === "nonexistent_local_date" ? "nonexistentDate" : "validation";
    default: return error.code === "NETWORK_ERROR" ? "network" : "server";
  }
}
