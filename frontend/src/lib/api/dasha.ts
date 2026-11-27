import { apiRequest, type ApiClientConfig } from "./client.ts";

export interface DashaBoundary {
  period_id: string;
  level: "MD" | "AD" | "PD";
  lord: string;
  start_utc: string;
  end_utc_exclusive: string;
}

export interface DashaPeriod extends DashaBoundary {
  children: DashaPeriod[];
}

export interface DashaResponse {
  snapshot_id: string;
  chart_id: string;
  timeline_id: string;
  method: "vimshottari-v1";
  time_certainty: "exact" | "approximate";
  is_conditional: boolean;
  year_days: number;
  profile_revision: number;
  is_current_profile_revision: boolean;
  birth_utc: string;
  start_utc: string;
  end_utc_exclusive: string;
  initial_balance: {
    nakshatra: string;
    lord: string;
    remaining_years: { numerator: number; denominator: number };
  };
  mahadashas: DashaPeriod[];
  lookup: {
    as_of: string | null;
    status: "active" | "before_birth" | "outside_cycle" | "not_requested";
    periods: {
      mahadasha: DashaBoundary;
      antardasha: DashaBoundary;
      pratyantardasha: DashaBoundary;
    } | null;
  };
}

export function readDasha(
  config: ApiClientConfig, snapshotId: string, asOf: string, signal: AbortSignal,
) {
  const query = new URLSearchParams({ as_of: asOf });
  return apiRequest<DashaResponse>(`/charts/${encodeURIComponent(snapshotId)}/dasha?${query}`, {
    config, signal,
  });
}
