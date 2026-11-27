import type {
  BirthProfile,
  BirthProfileCreatePayload,
  BirthProfileListResponse,
  BirthProfileUpdatePayload,
  BirthplaceSuggestion,
  BsConversionStatus,
  CalendarType,
  TimeCertainty,
} from "@/lib/kundali/types";
import { ApiClientError, apiRequest, type ApiClientConfig } from "./client.ts";

interface BackendBirthProfileDto {
  id: string;
  owner_id: string;
  label: string;
  input_calendar: CalendarType;
  entered_date: string;
  date_ad: string | null;
  bs_conversion_status: BsConversionStatus;
  time_certainty: TimeCertainty;
  time_local: string | null;
  place_name: string;
  latitude: number;
  longitude: number;
  timezone: string;
  created_at: string;
  updated_at: string;
}

interface BackendBirthProfileListDto {
  items: BackendBirthProfileDto[];
  total: number;
  limit: number;
  offset: number;
}

export function mapBirthProfileDto(dto: BackendBirthProfileDto): BirthProfile {
  return {
    id: dto.id,
    owner_id: dto.owner_id,
    label: dto.label,
    input_calendar: dto.input_calendar,
    entered_date: dto.entered_date,
    date_ad: dto.date_ad,
    bs_conversion_status: dto.bs_conversion_status,
    time_certainty: dto.time_certainty,
    time_local: dto.time_certainty === "unknown" ? null : dto.time_local,
    place_name: dto.place_name,
    latitude: dto.latitude,
    longitude: dto.longitude,
    timezone: dto.timezone,
    created_at: dto.created_at,
    updated_at: dto.updated_at,
    is_synthetic_sample: false,
  };
}

function assertNotSynthetic(candidate: { id?: string; is_synthetic_sample?: boolean }): void {
  if (candidate.is_synthetic_sample || candidate.id === "sample_north_london") {
    throw new ApiClientError({
      code: "VALIDATION_ERROR",
      status: 422,
      message: "Synthetic preview fixtures cannot be saved, updated, or deleted via the API.",
      validationMessages: [
        "Synthetic preview fixtures cannot be saved, updated, or deleted via the API.",
      ],
    });
  }
}

export function toCreateProfilePayload(
  input: BirthProfileCreatePayload & { id?: string; is_synthetic_sample?: boolean }
): BirthProfileCreatePayload {
  assertNotSynthetic(input);
  return {
    label: input.label.trim(),
    input_calendar: input.input_calendar,
    entered_date: input.entered_date.trim(),
    time_certainty: input.time_certainty,
    time_local: input.time_certainty === "unknown" ? null : (input.time_local?.trim() ?? null),
    ...(input.location_id === undefined ? {} : { location_id: input.location_id }),
    place_name: input.place_name.trim(),
    latitude: input.latitude,
    longitude: input.longitude,
    timezone: input.timezone.trim(),
  };
}

export function toUpdateProfilePayload(
  input: BirthProfileUpdatePayload & { id?: string; is_synthetic_sample?: boolean }
): BirthProfileUpdatePayload {
  assertNotSynthetic(input);
  const payload: BirthProfileUpdatePayload = {};

  if (input.label !== undefined) {
    payload.label = input.label.trim();
  }
  if (input.input_calendar !== undefined) {
    payload.input_calendar = input.input_calendar;
  }
  if (input.entered_date !== undefined) {
    payload.entered_date = input.entered_date.trim();
  }
  if (input.time_certainty !== undefined) {
    payload.time_certainty = input.time_certainty;
    if (input.time_certainty === "unknown") {
      payload.time_local = null;
    }
  }
  if (input.time_local !== undefined && input.time_certainty !== "unknown") {
    payload.time_local = input.time_local === null ? null : input.time_local.trim();
  }
  if (input.place_name !== undefined) {
    payload.place_name = input.place_name.trim();
  }
  if (input.location_id !== undefined) {
    payload.location_id = input.location_id;
  }
  if (input.latitude !== undefined) {
    payload.latitude = input.latitude;
  }
  if (input.longitude !== undefined) {
    payload.longitude = input.longitude;
  }
  if (input.timezone !== undefined) {
    payload.timezone = input.timezone.trim();
  }

  return payload;
}

export function searchBirthplaces(
  config: ApiClientConfig,
  query: string,
  signal: AbortSignal,
): Promise<BirthplaceSuggestion[]> {
  return apiRequest("/birthplaces/search", { method: "POST", body: { query }, config, signal });
}

export async function listProfiles(
  config: ApiClientConfig,
  query: { limit?: number; offset?: number } = {}
): Promise<BirthProfileListResponse> {
  const limit = query.limit ?? 50;
  const offset = query.offset ?? 0;
  const dto = await apiRequest<BackendBirthProfileListDto>(
    `/profiles?limit=${encodeURIComponent(String(limit))}&offset=${encodeURIComponent(String(offset))}`,
    { method: "GET", config }
  );
  return {
    items: dto.items.map(mapBirthProfileDto),
    total: dto.total,
    limit: dto.limit,
    offset: dto.offset,
  };
}

export async function createProfile(
  config: ApiClientConfig,
  payload: BirthProfileCreatePayload & { id?: string; is_synthetic_sample?: boolean }
): Promise<BirthProfile> {
  const sanitized = toCreateProfilePayload(payload);
  const dto = await apiRequest<BackendBirthProfileDto>("/profiles", {
    method: "POST",
    body: sanitized,
    config,
  });
  return mapBirthProfileDto(dto);
}

export async function updateProfile(
  config: ApiClientConfig,
  profileId: string,
  payload: BirthProfileUpdatePayload & { is_synthetic_sample?: boolean }
): Promise<BirthProfile> {
  assertNotSynthetic({ id: profileId, is_synthetic_sample: payload.is_synthetic_sample });
  const sanitized = toUpdateProfilePayload(payload);
  const dto = await apiRequest<BackendBirthProfileDto>(
    `/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PATCH",
      body: sanitized,
      config,
    }
  );
  return mapBirthProfileDto(dto);
}

export async function deleteProfile(config: ApiClientConfig, profileId: string): Promise<void> {
  assertNotSynthetic({ id: profileId });
  await apiRequest<null>(`/profiles/${encodeURIComponent(profileId)}`, {
    method: "DELETE",
    config,
  });
}
