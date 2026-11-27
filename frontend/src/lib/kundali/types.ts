export type Locale = "en" | "ne";

export type CalendarType = "AD" | "BS";

export type DisplayCalendarPreference = "AD" | "BS" | "BOTH";

export type TimeCertainty = "exact" | "approximate" | "unknown";

export type AyanamshaMode = "lahiri" | "lahiri_1940" | "raman" | "krishnamurti";

export type NodeType = "mean" | "true";

export type HouseSystem = "whole_sign";

export type DashaYearDays = 365.25 | 360 | 365.2425;

export type EphemerisSource = "swieph" | "moshier" | "mixed";

export type ChartPreset = "hamro_patro_compat";

export type ProvenanceDisplayStatus = EphemerisSource | "unknown";

export type ChartStyle = "north" | "south";

export type WorkspaceTab = "chat" | "dasha" | "transits";

export interface ChartSettings {
  ayanamsha: AyanamshaMode;
  house_system: HouseSystem;
  node_type: NodeType;
  year_days: DashaYearDays;
  preset: ChartPreset | null;
}

export interface ChartMetadata {
  ephemeris_source: EphemerisSource;
  julian_day: number;
  utc_offset_hours: number;
  datetime_utc_iso: string;
}

export interface ChartFactLagna {
  id: "f_lagna";
  type: "lagna";
  sign: string;
  sign_index: number;
  degree: number;
  longitude: number;
  nakshatra: string;
  pada: number;
}

export interface ChartFactPlacement {
  id: string;
  type: "placement";
  planet: string;
  sign: string;
  sign_index: number;
  degree: number;
  longitude: number;
  house: number;
  nakshatra: string;
  pada: number;
  retrograde: boolean;
  speed: number;
}

export interface ChartFactSensitivity {
  id: "f_lagna_sensitivity";
  type: "sensitivity";
  threshold_degrees: number;
  degree_in_sign: number;
  boundary_distance_degrees: number;
  note: string;
}

export type ChartFact = ChartFactLagna | ChartFactPlacement | ChartFactSensitivity;

export interface ChartFacts {
  /** Opaque calculation result identifier, independent of profile or account identity. */
  chart_id: string;
  engine_version: string;
  settings: ChartSettings;
  metadata: ChartMetadata;
  facts: ChartFact[];
}

export interface ChartCalculationResponse {
  profile_id: string;
  profile_updated_at: string;
  input_calendar: CalendarType;
  time_certainty: TimeCertainty;
  chart: ChartFacts;
}

export type BsConversionStatus = "resolved" | "awaiting_bs_conversion";

export type AccessTokenProvider = () => string | null | Promise<string | null>;

export interface BirthProfile {
  id: string;
  owner_id?: string;
  label: string;
  /** Original calendar in which the birth date was entered; persisted separately from display preference. */
  input_calendar: CalendarType;
  /** Raw entered date string in the original input calendar (YYYY-MM-DD). */
  entered_date: string;
  /** Resolved Gregorian AD date (null when entered in BS while bikram_sambat.py is unimplemented). */
  date_ad: string | null;
  /** Explicit backend conversion status for Bikram Sambat birth dates. */
  bs_conversion_status?: BsConversionStatus;
  /** Local birth time (HH:MM or HH:MM:SS); strictly null when time_certainty === "unknown". */
  time_local: string | null;
  place_name: string;
  latitude: number;
  longitude: number;
  timezone: string;
  time_certainty: TimeCertainty;
  created_at?: string;
  updated_at?: string;
  is_synthetic_sample?: boolean;
}

export interface BirthProfileCreatePayload {
  label: string;
  input_calendar: CalendarType;
  entered_date: string;
  time_certainty: TimeCertainty;
  time_local: string | null;
  location_id?: number;
  place_name: string;
  latitude: number;
  longitude: number;
  timezone: string;
}

export interface BirthplaceSuggestion {
  id: number;
  name: string;
  devanagari_names: string[];
  context: string;
  latitude: number;
  longitude: number;
  timezone: string;
}

export type BirthProfileUpdatePayload = Partial<BirthProfileCreatePayload>;

export interface BirthProfileListResponse {
  items: BirthProfile[];
  total: number;
  limit: number;
  offset: number;
}

export type ChartCalculationState =
  | "ready"
  | "awaiting_bs_conversion"
  | "unknown_time_unimplemented"
  | "awaiting_recompute"
  | "unavailable";

export type SettingsChangeScope = "none" | "dasha_only" | "full_chart";

export interface AllowlistedLlmPayload {
  facts: Array<
    | Pick<ChartFactLagna, "id" | "type" | "sign" | "degree" | "nakshatra" | "pada">
    | Pick<
        ChartFactPlacement,
        "id" | "type" | "planet" | "sign" | "house" | "degree" | "nakshatra" | "pada" | "retrograde"
      >
    | Pick<ChartFactSensitivity, "id" | "type" | "degree_in_sign" | "boundary_distance_degrees" | "note">
  >;
  conventions: Pick<ChartSettings, "ayanamsha" | "node_type" | "house_system" | "year_days">;
}
