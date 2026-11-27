import { SAMPLE_NORTH_LONDON_PROFILE } from "./sample-north-london.ts";
import type {
  AccessTokenProvider,
  BirthProfile,
  BirthProfileCreatePayload,
  CalendarType,
  TimeCertainty,
} from "./types.ts";

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

export type ProfileDateIssue =
  | "birth_date_format" | "invalid_ad_date" | "invalid_bs_date"
  | "bs_date_out_of_range" | "bs_date_unconfirmed";

export type ProfileTimeIssue = "dst_gap" | "dst_overlap";
export type ProfileLocationIssue = "invalid_birthplace" | "missing_birthplace" | "invalid_manual_location";
export type ProfileInputIssue = ProfileDateIssue | ProfileTimeIssue | ProfileLocationIssue;

export function isProfileDateIssue(value: string | null | undefined): value is ProfileDateIssue {
  return value === "birth_date_format" || value === "invalid_ad_date" ||
    value === "invalid_bs_date" || value === "bs_date_out_of_range" ||
    value === "bs_date_unconfirmed";
}

export function isProfileTimeIssue(value: ProfileInputIssue | null): value is ProfileTimeIssue {
  return value === "dst_gap" || value === "dst_overlap";
}

export function isProfileInputIssue(value: string | null): value is ProfileInputIssue {
  return isProfileDateIssue(value) || value === "dst_gap" || value === "dst_overlap" ||
    value === "invalid_birthplace" || value === "missing_birthplace" || value === "invalid_manual_location";
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
): { payload: BirthProfileCreatePayload; error: null } |
  { payload: null; error: string; dateIssue?: ProfileDateIssue; locationIssue?: ProfileLocationIssue } {
  const trimmedLabel = values.label.trim();
  if (!trimmedLabel) {
    return { payload: null, error: "Enter a profile label." };
  }

  const trimmedDate = values.enteredDate.trim().replace(/[०-९]/g, (digit) =>
    String(digit.charCodeAt(0) - "०".charCodeAt(0))
  );
  if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmedDate)) {
    return { payload: null, error: "Enter birth date in YYYY-MM-DD format.", dateIssue: "birth_date_format" };
  }
  const [year, month, day] = trimmedDate.split("-").map(Number);
  if (values.inputCalendar === "AD") {
    const date = new Date(`${trimmedDate}T00:00:00.000Z`);
    if (year === 0 || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== trimmedDate) {
      return { payload: null, error: "Invalid Gregorian AD birth date.", dateIssue: "invalid_ad_date" };
    }
  } else {
    if (year < 1975 || year > 2083) {
      return { payload: null, error: "Bikram Sambat year is out of range.", dateIssue: "bs_date_out_of_range" };
    }
    // Month-specific lengths, conversions and historical exclusions are server-owned.
    if (month < 1 || month > 12 || day < 1 || day > 32) {
      return { payload: null, error: "Invalid Bikram Sambat month or day.", dateIssue: "invalid_bs_date" };
    }
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
      locationIssue: "invalid_manual_location",
    };
  }

  const trimmedTimezone = values.timezone.trim();
  if (!trimmedTimezone) {
    return {
      payload: null,
      error: "Enter an explicit IANA timezone (e.g., Asia/Kathmandu, Europe/London, or UTC).",
      locationIssue: "invalid_manual_location",
    };
  }

  const latText = values.latitude.trim();
  const lonText = values.longitude.trim();
  if (!latText || !lonText) {
    return {
      payload: null,
      error: "Enter explicit latitude and longitude decimal coordinates.",
      locationIssue: "invalid_manual_location",
    };
  }

  const lat = Number(latText);
  const lon = Number(lonText);
  if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
    return { payload: null, error: "Latitude must be a finite number between -90 and 90.", locationIssue: "invalid_manual_location" };
  }
  if (!Number.isFinite(lon) || lon < -180 || lon > 180) {
    return { payload: null, error: "Longitude must be a finite number between -180 and 180.", locationIssue: "invalid_manual_location" };
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

export function applySessionCleared(state: ProfileWorkspaceState): ProfileWorkspaceState {
  return {
    savedProfiles: [],
    activeProfileId: state.previewSyntheticSample ? SAMPLE_NORTH_LONDON_PROFILE.id : null,
    previewSyntheticSample: state.previewSyntheticSample,
  };
}

export type WorkspaceSessionStatus =
  | "checking"
  | "authenticated"
  | "unauthenticated"
  | "unavailable";

export function reconcileWorkspaceSessionTransition(params: {
  sessionStatus: WorkspaceSessionStatus;
  userId: string | null;
  loadedOwnerKey: string | null;
}): "wait" | "clear" | "preserve" | "fetch" | "noop" {
  if (params.sessionStatus === "checking") {
    return "wait";
  }
  if (params.sessionStatus === "unavailable") {
    return "preserve";
  }
  if (params.sessionStatus === "unauthenticated") {
    return "clear";
  }
  const nextOwner = params.userId ?? "session-user";
  return params.loadedOwnerKey === nextOwner ? "noop" : "fetch";
}

export function classifyWorkspaceAuthError(params: {
  errorCode: string | null;
  liveSessionStatus?: WorkspaceSessionStatus | null;
}): "unavailable" | "unauthenticated" | "other" {
  if (params.errorCode !== "AUTH_REQUIRED" && params.errorCode !== "UNAUTHORIZED") {
    return "other";
  }
  if (params.liveSessionStatus === "unavailable") {
    return "unavailable";
  }
  return "unauthenticated";
}

export async function fetchWorkspaceProfilesSafely(params: {
  getAccessToken?: AccessTokenProvider;
  fetchList: (resolvedToken: string) => Promise<BirthProfile[]>;
  liveSessionStatus?: () => WorkspaceSessionStatus | null;
  unavailableFallbackMessage: string;
}): Promise<
  | { kind: "loaded"; items: BirthProfile[] }
  | { kind: "unauthenticated"; message: string | null }
  | { kind: "unavailable"; message: string }
  | { kind: "error"; message: string }
> {
  if (!params.getAccessToken) {
    return { kind: "unauthenticated", message: null };
  }
  try {
    const rawToken = await params.getAccessToken();
    const validToken = typeof rawToken === "string" ? rawToken.trim() : "";
    if (!validToken) {
      const outcome = classifyWorkspaceAuthError({
        errorCode: "AUTH_REQUIRED",
        liveSessionStatus: params.liveSessionStatus?.() ?? null,
      });
      return outcome === "unavailable"
        ? { kind: "unavailable", message: params.unavailableFallbackMessage }
        : { kind: "unauthenticated", message: null };
    }
    const items = await params.fetchList(validToken);
    return { kind: "loaded", items };
  } catch (err) {
    const code =
      err && typeof err === "object" && "code" in err
        ? String((err as { code?: unknown }).code)
        : null;
    const outcome = classifyWorkspaceAuthError({
      errorCode: code,
      liveSessionStatus: params.liveSessionStatus?.() ?? null,
    });
    if (outcome === "unavailable") {
      return { kind: "unavailable", message: params.unavailableFallbackMessage };
    }
    if (outcome === "unauthenticated") {
      return {
        kind: "unauthenticated",
        message: err instanceof Error ? err.message : "Authentication required.",
      };
    }
    return {
      kind: "error",
      message: err instanceof Error ? err.message : "Unable to load saved birth profiles.",
    };
  }
}

export interface ProfileLoadCoordinatorSnapshot {
  generation: number;
  sessionStatus: WorkspaceSessionStatus;
  ownerKey: string | null;
  loadedOwnerKey: string | null;
}

export interface ProfileLoadCoordinator {
  getSnapshot(): ProfileLoadCoordinatorSnapshot;
  syncSessionContext(params: {
    status: WorkspaceSessionStatus;
    ownerKey: string | null;
  }): { shouldClearWorkspace: boolean; shouldFetch: boolean };
  invalidate(): void;
  markExplicitAuthSuccess(ownerKey: string, expectedGeneration: number): boolean;
  isCurrentRequest(params: {
    requestGeneration: number;
    ownerKey: string;
    getLiveContext?: () => { status: WorkspaceSessionStatus; ownerKey: string | null } | null;
  }): boolean;
  startLoad(params: {
    ownerKey: string;
    getAccessToken?: AccessTokenProvider;
    fetchList: (resolvedToken: string) => Promise<BirthProfile[]>;
    getLiveContext?: () => { status: WorkspaceSessionStatus; ownerKey: string | null } | null;
    unavailableFallbackMessage: string;
    onLoadingChange: (isLoading: boolean) => void;
    onLoaded: (items: BirthProfile[]) => void;
    onUnauthenticated: (message: string | null) => void;
    onUnavailable: (message: string) => void;
    onError: (message: string) => void;
  }): Promise<BirthProfile[] | null>;
}

/**
 * Tracks workspace session generation and owner identity across async profile fetches
 * so stale responses or errors from an earlier user/session can never overwrite the active user.
 */
export function createProfileLoadCoordinator(): ProfileLoadCoordinator {
  let generation = 0;
  let sessionStatus: WorkspaceSessionStatus = "checking";
  let currentOwnerKey: string | null = null;
  let loadedOwnerKey: string | null = null;
  let activeRequestId = 0;
  let inFlight: {
    requestId: number;
    generation: number;
    ownerKey: string;
    promise: Promise<BirthProfile[] | null>;
  } | null = null;

  function syncSessionContext(params: {
    status: WorkspaceSessionStatus;
    ownerKey: string | null;
  }): { shouldClearWorkspace: boolean; shouldFetch: boolean } {
    const nextStatus = params.status;
    if (nextStatus === "unauthenticated") {
      const hadActiveSession =
        sessionStatus !== "unauthenticated" ||
        currentOwnerKey !== null ||
        loadedOwnerKey !== null ||
        inFlight !== null;
      if (hadActiveSession) {
        generation += 1;
        inFlight = null;
      }
      sessionStatus = "unauthenticated";
      currentOwnerKey = null;
      loadedOwnerKey = null;
      return { shouldClearWorkspace: true, shouldFetch: false };
    }

    if (nextStatus === "checking") {
      if (currentOwnerKey !== null && params.ownerKey !== currentOwnerKey) {
        generation += 1;
        loadedOwnerKey = null;
        inFlight = null;
      }
      sessionStatus = "checking";
      currentOwnerKey = params.ownerKey;
      return { shouldClearWorkspace: false, shouldFetch: false };
    }

    if (nextStatus === "unavailable") {
      sessionStatus = "unavailable";
      return { shouldClearWorkspace: false, shouldFetch: false };
    }

    const nextOwner = params.ownerKey ?? "session-user";
    const ownerChanged = currentOwnerKey !== null && currentOwnerKey !== nextOwner;
    if (ownerChanged || sessionStatus === "unauthenticated") {
      generation += 1;
      loadedOwnerKey = null;
      inFlight = null;
    }
    sessionStatus = "authenticated";
    currentOwnerKey = nextOwner;
    return {
      shouldClearWorkspace: ownerChanged,
      shouldFetch: loadedOwnerKey !== nextOwner,
    };
  }

  function invalidate(): void {
    generation += 1;
    sessionStatus = "unauthenticated";
    currentOwnerKey = null;
    loadedOwnerKey = null;
    inFlight = null;
  }

  function markExplicitAuthSuccess(ownerKey: string, expectedGeneration: number): boolean {
    if (expectedGeneration !== generation || currentOwnerKey !== ownerKey) {
      return false;
    }
    if (sessionStatus === "unauthenticated") {
      return false;
    }
    sessionStatus = "authenticated";
    return true;
  }

  function isCurrentRequest(params: {
    requestGeneration: number;
    ownerKey: string;
    getLiveContext?: () => { status: WorkspaceSessionStatus; ownerKey: string | null } | null;
  }): boolean {
    if (params.requestGeneration !== generation) {
      return false;
    }
    if (sessionStatus !== "authenticated" || currentOwnerKey !== params.ownerKey) {
      return false;
    }
    const live = params.getLiveContext?.();
    if (live) {
      if (live.status !== "authenticated") {
        return false;
      }
      if ((live.ownerKey ?? "session-user") !== params.ownerKey) {
        return false;
      }
    }
    return true;
  }

  function isSameGenerationAndOwner(params: {
    requestGeneration: number;
    ownerKey: string;
    getLiveContext?: () => { status: WorkspaceSessionStatus; ownerKey: string | null } | null;
  }): boolean {
    if (params.requestGeneration !== generation || currentOwnerKey !== params.ownerKey) {
      return false;
    }
    const live = params.getLiveContext?.();
    if (live) {
      if (live.status === "unauthenticated") {
        return false;
      }
      if (live.ownerKey !== null && (live.ownerKey ?? "session-user") !== params.ownerKey) {
        return false;
      }
    }
    return true;
  }

  function startLoad(params: {
    ownerKey: string;
    getAccessToken?: AccessTokenProvider;
    fetchList: (resolvedToken: string) => Promise<BirthProfile[]>;
    getLiveContext?: () => { status: WorkspaceSessionStatus; ownerKey: string | null } | null;
    unavailableFallbackMessage: string;
    onLoadingChange: (isLoading: boolean) => void;
    onLoaded: (items: BirthProfile[]) => void;
    onUnauthenticated: (message: string | null) => void;
    onUnavailable: (message: string) => void;
    onError: (message: string) => void;
  }): Promise<BirthProfile[] | null> {
    if (inFlight && inFlight.ownerKey === params.ownerKey && inFlight.generation === generation) {
      return inFlight.promise;
    }

    const reqGeneration = generation;
    const reqOwnerKey = params.ownerKey;
    const reqId = ++activeRequestId;

    let promise: Promise<BirthProfile[] | null> | null = null;
    promise = (async (): Promise<BirthProfile[] | null> => {
      await Promise.resolve();
      if (
        !isSameGenerationAndOwner({
          requestGeneration: reqGeneration,
          ownerKey: reqOwnerKey,
          getLiveContext: params.getLiveContext,
        })
      ) {
        return null;
      }
      if (activeRequestId === reqId) {
        params.onLoadingChange(true);
      }

      try {
        const result = await fetchWorkspaceProfilesSafely({
          getAccessToken: params.getAccessToken,
          unavailableFallbackMessage: params.unavailableFallbackMessage,
          liveSessionStatus: () => params.getLiveContext?.()?.status ?? sessionStatus,
          fetchList: async (validToken) => {
            markExplicitAuthSuccess(reqOwnerKey, reqGeneration);
            return params.fetchList(validToken);
          },
        });

        if (result.kind === "loaded") {
          if (
            !isCurrentRequest({
              requestGeneration: reqGeneration,
              ownerKey: reqOwnerKey,
              getLiveContext: params.getLiveContext,
            })
          ) {
            return null;
          }
          loadedOwnerKey = reqOwnerKey;
          params.onLoaded(result.items);
          return result.items;
        }

        if (
          !isSameGenerationAndOwner({
            requestGeneration: reqGeneration,
            ownerKey: reqOwnerKey,
            getLiveContext: params.getLiveContext,
          })
        ) {
          return null;
        }

        if (result.kind === "unauthenticated") {
          params.onUnauthenticated(result.message);
          return null;
        }

        if (result.kind === "unavailable") {
          params.onUnavailable(result.message);
          return null;
        }

        params.onError(result.message);
        return null;
      } finally {
        if (inFlight?.requestId === reqId) {
          inFlight = null;
        }
        if (activeRequestId === reqId) {
          params.onLoadingChange(false);
        }
      }
    })();

    inFlight = { requestId: reqId, generation: reqGeneration, ownerKey: reqOwnerKey, promise };
    return promise;
  }

  return {
    getSnapshot: () => ({
      generation,
      sessionStatus,
      ownerKey: currentOwnerKey,
      loadedOwnerKey,
    }),
    syncSessionContext,
    invalidate,
    markExplicitAuthSuccess,
    isCurrentRequest,
    startLoad,
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
