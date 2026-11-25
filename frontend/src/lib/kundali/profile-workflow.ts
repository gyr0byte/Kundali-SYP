import { SAMPLE_NORTH_LONDON_PROFILE } from "./sample-north-london.ts";
import type { BirthProfile, BirthProfileCreatePayload, CalendarType, TimeCertainty } from "./types.ts";

export interface ProfileWorkspaceState {
  savedProfiles: BirthProfile[];
  activeProfileId: string | null;
  previewSyntheticSample: boolean;
}

export interface BirthProfileFormValues {
  label: string;
  inputCalendar: CalendarType;
  enteredDate: string;
  certainty: TimeCertainty;
  timeLocal: string;
  placeName: string;
  timezone: string;
  latitude: string;
  longitude: string;
}

/**
 * Blank defaults for new birth profiles. Never prefills Kathmandu, coordinates,
 * timezone, or birth dates; all identity and location inputs must be explicit.
 */
export function getInitialProfileFormValues(
  initialProfile?: BirthProfile | null
): BirthProfileFormValues {
  if (initialProfile) {
    return {
      label: initialProfile.label,
      inputCalendar: initialProfile.input_calendar,
      enteredDate: initialProfile.entered_date,
      certainty: initialProfile.time_certainty,
      timeLocal: initialProfile.time_local ?? "",
      placeName: initialProfile.place_name,
      timezone: initialProfile.timezone,
      latitude: String(initialProfile.latitude),
      longitude: String(initialProfile.longitude),
    };
  }
  return {
    label: "",
    inputCalendar: "BS",
    enteredDate: "",
    certainty: "exact",
    timeLocal: "",
    placeName: "",
    timezone: "",
    latitude: "",
    longitude: "",
  };
}

export function validateProfileFormInput(
  values: BirthProfileFormValues
): { payload: BirthProfileCreatePayload; error: null } | { payload: null; error: string } {
  const trimmedLabel = values.label.trim();
  if (!trimmedLabel) {
    return { payload: null, error: "Enter a profile label." };
  }

  const trimmedDate = values.enteredDate.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmedDate)) {
    return { payload: null, error: "Enter birth date in YYYY-MM-DD format." };
  }

  const trimmedTime = values.timeLocal.trim();
  if (values.certainty !== "unknown" && !/^\d{2}:\d{2}(:\d{2})?$/.test(trimmedTime)) {
    return {
      payload: null,
      error: "Enter local birth time (HH:MM) or mark time certainty as Unknown.",
    };
  }

  const trimmedPlace = values.placeName.trim();
  if (!trimmedPlace) {
    return {
      payload: null,
      error: "Enter an explicit birth place name.",
    };
  }

  const trimmedTimezone = values.timezone.trim();
  if (!trimmedTimezone) {
    return {
      payload: null,
      error: "Enter an explicit IANA timezone (e.g., Asia/Kathmandu, Europe/London, or UTC).",
    };
  }

  const latText = values.latitude.trim();
  const lonText = values.longitude.trim();
  if (!latText || !lonText) {
    return {
      payload: null,
      error: "Enter explicit latitude and longitude decimal coordinates.",
    };
  }

  const lat = Number(latText);
  const lon = Number(lonText);
  if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
    return { payload: null, error: "Latitude must be a finite number between -90 and 90." };
  }
  if (!Number.isFinite(lon) || lon < -180 || lon > 180) {
    return { payload: null, error: "Longitude must be a finite number between -180 and 180." };
  }

  return {
    payload: {
      label: trimmedLabel,
      input_calendar: values.inputCalendar,
      entered_date: trimmedDate,
      time_certainty: values.certainty,
      time_local: values.certainty === "unknown" ? null : trimmedTime,
      place_name: trimmedPlace,
      latitude: lat === 0 ? 0 : lat,
      longitude: lon === 0 ? 0 : lon,
      timezone: trimmedTimezone,
    },
    error: null,
  };
}

export function createInitialWorkspaceState(): ProfileWorkspaceState {
  return {
    savedProfiles: [],
    activeProfileId: null,
    previewSyntheticSample: false,
  };
}

export function applyLoadedProfiles(
  state: ProfileWorkspaceState,
  loadedProfiles: BirthProfile[]
): ProfileWorkspaceState {
  const cleanSaved = loadedProfiles.filter(
    (p) => !p.is_synthetic_sample && p.id !== SAMPLE_NORTH_LONDON_PROFILE.id
  );
  const keepCurrentSaved = cleanSaved.some((p) => p.id === state.activeProfileId);
  const keepSample =
    state.previewSyntheticSample && state.activeProfileId === SAMPLE_NORTH_LONDON_PROFILE.id;

  return {
    savedProfiles: cleanSaved,
    activeProfileId: keepSample
      ? SAMPLE_NORTH_LONDON_PROFILE.id
      : keepCurrentSaved
        ? state.activeProfileId
        : (cleanSaved[0]?.id ?? null),
    previewSyntheticSample: state.previewSyntheticSample,
  };
}

export function applyCreatedProfile(
  state: ProfileWorkspaceState,
  created: BirthProfile
): ProfileWorkspaceState {
  const withoutDuplicate = state.savedProfiles.filter((p) => p.id !== created.id);
  return {
    savedProfiles: [{ ...created, is_synthetic_sample: false }, ...withoutDuplicate],
    activeProfileId: created.id,
    previewSyntheticSample: state.previewSyntheticSample,
  };
}

export function applyUpdatedProfile(
  state: ProfileWorkspaceState,
  updated: BirthProfile
): ProfileWorkspaceState {
  return {
    savedProfiles: state.savedProfiles.map((p) =>
      p.id === updated.id ? { ...updated, is_synthetic_sample: false } : p
    ),
    activeProfileId: updated.id,
    previewSyntheticSample: state.previewSyntheticSample,
  };
}

export function applyDeletedProfile(
  state: ProfileWorkspaceState,
  deletedId: string
): ProfileWorkspaceState {
  const remaining = state.savedProfiles.filter((p) => p.id !== deletedId);
  let nextActiveId = state.activeProfileId;
  if (state.activeProfileId === deletedId) {
    nextActiveId = remaining[0]?.id ?? (state.previewSyntheticSample ? SAMPLE_NORTH_LONDON_PROFILE.id : null);
  }
  return {
    savedProfiles: remaining,
    activeProfileId: nextActiveId,
    previewSyntheticSample: state.previewSyntheticSample,
  };
}

export function activateSyntheticSamplePreview(
  state: ProfileWorkspaceState
): ProfileWorkspaceState {
  return {
    savedProfiles: state.savedProfiles,
    activeProfileId: SAMPLE_NORTH_LONDON_PROFILE.id,
    previewSyntheticSample: true,
  };
}

export function resolveVisibleProfiles(state: ProfileWorkspaceState): BirthProfile[] {
  return state.previewSyntheticSample
    ? [...state.savedProfiles, SAMPLE_NORTH_LONDON_PROFILE]
    : [...state.savedProfiles];
}

export function resolveActiveProfile(state: ProfileWorkspaceState): BirthProfile | null {
  if (!state.activeProfileId) {
    return null;
  }
  if (
    state.previewSyntheticSample &&
    state.activeProfileId === SAMPLE_NORTH_LONDON_PROFILE.id
  ) {
    return SAMPLE_NORTH_LONDON_PROFILE;
  }
  return state.savedProfiles.find((p) => p.id === state.activeProfileId) ?? null;
}
