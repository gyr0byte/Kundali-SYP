"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useOptionalAuthSession } from "@/components/auth/AuthSessionProvider";
import { calculateChart, getChartIssue, matchesChartProfile, type ChartIssue } from "@/lib/api/charts";
import { DashaTimeline, type DashaLabels } from "./DashaTimeline";
import { ApiClientError } from "@/lib/api/client";
import {
  createProfile,
  deleteProfile,
  listProfiles,
  updateProfile,
} from "@/lib/api/profiles";
import type { AuthSessionStatus } from "@/lib/auth/session-client";
import {
  classifyLogoutAllOutcome,
  classifyLogoutOutcome,
  type LogoutOutcomeBanner,
} from "@/lib/auth/ui-helpers";
import {
  classifySettingsChange,
  formatDegreeInSign,
  getLagnaFact,
  getPlacementFacts,
  getProvenanceStatus,
  getSensitivityFact,
  isUnknownTimeProfile,
} from "@/lib/kundali/chart-helpers";
import {
  AYANAMSHA_OPTIONS, NAKSHATRA_NE, NODE_TYPE_OPTIONS, PLANET_LABELS, YEAR_DAYS_OPTIONS, ZODIAC_SIGNS,
} from "@/lib/kundali/constants";
import {
  activateSyntheticSamplePreview,
  applyCreatedProfile,
  applyDeletedProfile,
  applyLoadedProfiles,
  applySessionCleared,
  applyUpdatedProfile,
  classifyWorkspaceAuthError,
  createInitialWorkspaceState,
  createProfileLoadCoordinator,
  isProfileInputIssue,
  resolveActiveProfile,
  resolveVisibleProfiles,
  type ProfileWorkspaceState,
  type ProfileDateIssue,
  type ProfileInputIssue,
  type ProfileTimeIssue,
} from "@/lib/kundali/profile-workflow";
import {
  SAMPLE_NORTH_LONDON_CHART_FACTS,
  SAMPLE_NORTH_LONDON_PROFILE,
} from "@/lib/kundali/sample-north-london";
import type {
  AccessTokenProvider,
  BirthProfile,
  BirthProfileCreatePayload,
  ChartCalculationState,
  ChartCalculationResponse,
  ChartFacts,
  ChartSettings,
  ChartStyle,
  DisplayCalendarPreference,
  Locale,
} from "@/lib/kundali/types";
import { BirthProfileForm } from "./BirthProfileForm";
import { CalculationSettingsPopover } from "./CalculationSettingsPopover";
import { MoonWindowPanel, type MoonWindowLabels } from "./MoonWindowPanel";
import { KundaliChartPlaceholder, KundaliSvgChart } from "./KundaliSvgChart";
import { PlanetaryTable, PlanetaryTableSkeleton } from "./PlanetaryTable";

export interface WorkspaceMessages {
  brandName: string;
  brandNative: string;
  tagline: string;
  disclaimer: string;
  navWorkspace: string;
  navProfiles: string;
  navPrivacy: string;
  workspaceIntro: string;
  profilesIntro: string;
  preferencesIntro: string;
  workspaceNavigation: string;
  navigationToggle: string;
  accountMenu: string;
  plannedHeading: string;
  dasha: DashaLabels;
  plannedTransits: string;
  plannedAi: string;
  plannedCompatibility: string;
  privacyHeading: string;
  privacyBody: string;
  calculateDetails: string;
  chartIdentifier: string;
  engineVersionLabel: string;
  emptyWorkspace: string;
  openProfiles: string;
  profileLoadFailed: string;
  profileSaveFailed: string;
  profileDeleteFailed: string;
  localeLabel: string;
  provenanceSwieph: string;
  provenanceMoshier: string;
  provenanceMixed: string;
  provenanceUnknown: string;
  profileLabel: string;
  newProfileButton: string;
  loadSampleButton: string;
  restoreSampleButton: string;
  syntheticPreviewButton: string;
  enteredInPrefix: string;
  displayCalendarLabel: string;
  displayAd: string;
  displayBs: string;
  displayBoth: string;
  bsDisplayPending: string;
  timeExact: string;
  timeApproximate: string;
  timeUnknown: string;
  settingsButton: string;
  settingsTitle: string;
  presetLabel: string;
  presetStandard: string;
  presetHamro: string;
  ayanamshaLabel: string;
  nodeTypeLabel: string;
  houseSystemLabel: string;
  houseSystemFixedValue: string;
  yearDaysLabel: string;
  scopeNone: string;
  scopeDashaOnly: string;
  scopeFullChart: string;
  discard: string;
  applySettings: string;
  close: string;
  authRequiredBannerTitle: string;
  authRequiredBannerBody: string;
  authFormLockedNotice: string;
  sessionUnavailableBannerTitle: string;
  sessionUnavailableBannerBody: string;
  retrySessionButton: string;
  signInNavButton: string;
  createAccountNavButton: string;
  sessionCheckingHeaderLabel: string;
  sessionUnavailableHeaderLabel: string;
  signedInRolePrefix: string;
  signOutButton: string;
  signingOutButton: string;
  signOutAllButton: string;
  signingOutAllButton: string;
  logoutConfirmTitle: string;
  logoutConfirmBody: string;
  logoutConfirmCancel: string;
  logoutConfirmProceed: string;
  logoutOutcomeConfirmed: string;
  logoutOutcomeUnconfirmed: string;
  logoutOutcomeNetworkError: string;
  logoutAllConfirmedNotice: string;
  logoutAllFailedNotice: string;
  loadingProfilesNotice: string;
  retryLoadButton: string;
  editProfileButton: string;
  deleteProfileButton: string;
  deleteConfirmPrompt: string;
  deleteConfirmButton: string;
  deleteCancelButton: string;
  profileCreatedNotice: string;
  profileUpdatedNotice: string;
  profileDeletedNotice: string;
  savedProfileBsStatusBadge: string;
  sampleBannerTitle: string;
  sampleBannerBody: string;
  approxBannerTitle: string;
  approxBannerBody: string;
  unknownTimeBannerTitle: string;
  unknownTimeBannerBody: string;
  lagnaSensitivityTitle: string;
  awaitingRecomputeBody: string;
  calculateChart: string;
  calculatingChart: string;
  chartCalculated: string;
  chartEmpty: string;
  selectProfileForChart: string;
  readyToCalculate: string;
  recalculateChart: string;
  retryChart: string;
  reloadChartProfiles: string;
  lagnaSensitivityBody: string;
  skipToWorkspace: string;
  compatibilityUnavailable: string;
  chartIssues: Record<ChartIssue, string>;
  moonWindow: MoonWindowLabels;
  dashaOnlyNotice: string;
  chartSectionTitle: string;
  northLabel: string;
  southLabel: string;
  houseWord: string;
  lagnaShort: string;
  tableSectionTitle: string;
  tableCaption: string;
  colBody: string;
  colSign: string;
  colDegree: string;
  colHouse: string;
  colNakshatra: string;
  colMotion: string;
  colFactId: string;
  retrogradeLabel: string;
  directLabel: string;
  lagnaName: string;
  padaWord: string;
  tableEmptyNotice: string;
  selectedFactLabel: string;
  clearSelection: string;
  tabChat: string;
  tabDasha: string;
  tabTransits: string;
  stubBadge: string;
  chatContractTitle: string;
  chatContractBody: string;
  chatAllowlistTitle: string;
  chatExcludedTitle: string;
  chatExcludedList: string;
  chatComposerPlaceholder: string;
  chatSubmitDisabled: string;
  dashaContractTitle: string;
  dashaContractBody: string;
  dashaHierarchyLabel: string;
  dashaConventionLabel: string;
  transitsContractTitle: string;
  transitsContractBody: string;
  unavailableNoChart: string;
  formTitle: string;
  editFormTitle: string;
  formSubtitle: string;
  formLabel: string;
  formLabelPlaceholder: string;
  formInputCalendar: string;
  formDate: string;
  formDateHint: string;
  formBsRange: string;
  formDateErrors: Record<ProfileDateIssue, string>;
  formTimeErrors: Record<ProfileTimeIssue, string>;
  formLocation: import("./BirthplaceSearch").BirthplaceLabels;
  convertedAdLabel: string;
  formCertainty: string;
  formTime: string;
  formTimeUnknownNote: string;
  formPlace: string;
  formPlacePlaceholder: string;
  formTimezone: string;
  formTimezonePlaceholder: string;
  formLatitude: string;
  formLongitude: string;
  formLatitudePlaceholder: string;
  formLongitudePlaceholder: string;
  formCoordinatesNote: string;
  formSubmit: string;
  editFormSubmit: string;
  formSaving: string;
  formDeleting: string;
  formCancel: string;
  mobileViewChart: string;
  mobileViewSecondary: string;
}

interface UserChartWorkspaceProps {
  messagesByLocale: Record<Locale, WorkspaceMessages>;
  /** Optional injected access token provider for tests or custom embedding. */
  getAccessToken?: AccessTokenProvider;
  /** Optional single-retry 401 refresh callback for tests or custom embedding. */
  onUnauthorizedRefresh?: (failedToken?: string) => Promise<string | null>;
  /** Optional API base URL override for environment wiring or tests. */
  apiBaseUrl?: string;
}

type WorkspacePage = "chart" | "profiles" | "settings";

const DEFAULT_SETTINGS: ChartSettings = {
  ayanamsha: "lahiri",
  house_system: "whole_sign",
  node_type: "mean",
  year_days: 365.25,
  preset: null,
};

function getSamplePreview(
  profile: BirthProfile | null,
  settings: ChartSettings
): { state: ChartCalculationState; chart: ChartFacts | null } {
  if (profile?.is_synthetic_sample && profile.id === SAMPLE_NORTH_LONDON_PROFILE.id) {
    const base = SAMPLE_NORTH_LONDON_CHART_FACTS.settings;
    const ephemerisMatches =
      settings.ayanamsha === base.ayanamsha &&
      settings.node_type === base.node_type &&
      settings.preset === base.preset;
    if (!ephemerisMatches) {
      return { state: "awaiting_recompute", chart: null };
    }
    return { state: "ready", chart: SAMPLE_NORTH_LONDON_CHART_FACTS };
  }
  return { state: "unavailable", chart: null };
}

type ChartRun =
  | { status: "idle" | "loading" }
  | { status: "error"; issue: ChartIssue }
  | { status: "success"; result: ChartCalculationResponse; snapshotId: string | null };

export function UserChartWorkspace({
  messagesByLocale,
  getAccessToken,
  onUnauthorizedRefresh,
  apiBaseUrl,
}: UserChartWorkspaceProps) {
  const session = useOptionalAuthSession();
  const hasExplicitTokenProp = getAccessToken !== undefined;
  const effectiveGetAccessToken = hasExplicitTokenProp
    ? getAccessToken
    : session?.getAccessToken;
  const effectiveOnUnauthorizedRefresh =
    onUnauthorizedRefresh ?? (hasExplicitTokenProp ? undefined : session?.onUnauthorizedRefresh);

  const [locale, setLocale] = useState<Locale>("en");
  const [profileState, setProfileState] = useState<ProfileWorkspaceState>(
    createInitialWorkspaceState
  );
  const [localAuthStatus, setLocalAuthStatus] = useState<AuthSessionStatus>(() =>
    hasExplicitTokenProp ? "checking" : session ? session.status : "unauthenticated"
  );
  const authStatus: AuthSessionStatus =
    !hasExplicitTokenProp && session ? session.status : localAuthStatus;
  const [isLoadingProfiles, setIsLoadingProfiles] = useState<boolean>(false);
  const [formMode, setFormMode] = useState<"closed" | "create" | "edit">("closed");
  const [isSubmittingForm, setIsSubmittingForm] = useState<boolean>(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [isDeletingProfile, setIsDeletingProfile] = useState<boolean>(false);
  const [isSigningOut, setIsSigningOut] = useState<boolean>(false);
  const [isSigningOutAll, setIsSigningOutAll] = useState<boolean>(false);
  const [showLogoutAllConfirm, setShowLogoutAllConfirm] = useState<boolean>(false);
  const [sessionFeedback, setSessionFeedback] = useState<LogoutOutcomeBanner | null>(null);
  const [apiErrorBanner, setApiErrorBanner] = useState<string | null>(null);
  const [formServerErrors, setFormServerErrors] = useState<readonly string[] | ProfileInputIssue>([]);
  const [profileActionNotice, setProfileActionNotice] = useState<
    "profileCreatedNotice" | "profileUpdatedNotice" | "profileDeletedNotice" | null
  >(null);

  const [displayCalendar, setDisplayCalendar] = useState<DisplayCalendarPreference>("AD");
  const [appliedSettings, setAppliedSettings] = useState<ChartSettings>(DEFAULT_SETTINGS);
  const [stagedSettings, setStagedSettings] = useState<ChartSettings>(DEFAULT_SETTINGS);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const settingsTriggerRef = useRef<HTMLButtonElement>(null);
  const chartRequestRef = useRef<AbortController | null>(null);
  const [showDashaNotice, setShowDashaNotice] = useState(false);
  const [chartStyle, setChartStyle] = useState<ChartStyle>("north");
  const [page, setPage] = useState<WorkspacePage>("chart");
  const [navigationOpen, setNavigationOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDetailsElement>(null);
  const logoutCancelRef = useRef<HTMLButtonElement>(null);
  const workspaceMainRef = useRef<HTMLElement>(null);
  const [highlightedFactId, setHighlightedFactId] = useState<string | null>(null);

  const [profileLoadCoordinator] = useState(createProfileLoadCoordinator);
  const explicitProviderSeqRef = useRef<number>(1);
  const prevExplicitTokenProviderRef = useRef<AccessTokenProvider | undefined>(getAccessToken);

  const t = messagesByLocale[locale];
  const pageLabels = {
    chart: { title: t.navWorkspace, description: t.workspaceIntro },
    profiles: { title: t.navProfiles, description: t.profilesIntro },
    settings: { title: t.navPrivacy, description: t.preferencesIntro },
  };
  const isAuthenticated = authStatus === "authenticated";
  const displayedProfileState =
    authStatus === "unauthenticated" ? applySessionCleared(profileState) : profileState;
  const visibleProfiles = resolveVisibleProfiles(displayedProfileState);
  const activeProfile = resolveActiveProfile(displayedProfileState);
  const profileChoices = page === "profiles" ? displayedProfileState.savedProfiles : visibleProfiles;
  const summaryProfile = page === "profiles" && activeProfile?.is_synthetic_sample ? null : activeProfile;
  const chartProfile = isAuthenticated && activeProfile && !activeProfile.is_synthetic_sample &&
    (hasExplicitTokenProp || activeProfile.owner_id === session?.user?.id)
    ? activeProfile
    : null;
  // Dasha year length does not change placements. A new calculation sends
  // the latest applied year length; a displayed result keeps its own settings.
  const chartContext = chartProfile ? JSON.stringify([
    chartProfile.owner_id, chartProfile.id, chartProfile.updated_at, chartProfile.time_certainty,
    appliedSettings.ayanamsha,
    ...(chartProfile.time_certainty === "unknown" ? [] :
      [appliedSettings.house_system, appliedSettings.node_type, appliedSettings.preset]),
  ]) : null;
  const [chartState, setChartState] = useState<{
    context: string | null;
    provider: AccessTokenProvider | undefined;
    run: ChartRun;
  }>(
    { context: chartContext, provider: getAccessToken, run: { status: "idle" } }
  );
  const sameContext = chartState.context === chartContext && chartState.provider === getAccessToken;
  const chartRun: ChartRun = sameContext ? chartState.run : { status: "idle" };
  if (!sameContext) {
    setChartState({ context: chartContext, provider: getAccessToken, run: chartRun });
    if (highlightedFactId) setHighlightedFactId(null);
  }

  useLayoutEffect(() => {
    return () => {
      chartRequestRef.current?.abort();
      chartRequestRef.current = null;
    };
  }, [chartContext, getAccessToken]);

  const samplePreview = getSamplePreview(activeProfile, appliedSettings);
  const result = chartRun.status === "success" ? chartRun.result : null;
  const moon = result?.time_certainty === "unknown" ? result.moon : null;
  const chart = result && result.time_certainty !== "unknown" ? result.chart : samplePreview.chart;
  const natal = result && result.time_certainty !== "unknown" ? result.chart : null;
  const snapshotId = chartRun.status === "success" ? chartRun.snapshotId : null;
  const dashaNeedsRecalculation = natal !== null && natal.settings.year_days !== appliedSettings.year_days;
  const calcState = result ? "ready" : samplePreview.state;
  const resolvedSettings = chart?.settings ?? appliedSettings;
  const provenanceStatus = moon?.ephemeris_source ?? getProvenanceStatus(chart, calcState);
  const unknownTimeMode = isUnknownTimeProfile(activeProfile);
  const sensitivityFact = getSensitivityFact(chart);

  async function handleCalculateChart() {
    if (!chartProfile || chartRequestRef.current || isLoadingProfiles) return;
    const request = new AbortController();
    chartRequestRef.current = request;
    setHighlightedFactId(null);
    const context = { context: chartContext, provider: getAccessToken };
    setChartState({ ...context, run: { status: "loading" } });
    try {
      let snapshot: string | null = null;
      const response = await calculateChart({
        getAccessToken: effectiveGetAccessToken,
        onUnauthorizedRefresh: effectiveOnUnauthorizedRefresh,
        baseUrl: apiBaseUrl,
      }, chartProfile, appliedSettings, request.signal, (id) => { snapshot = id; });
      if (request.signal.aborted) return;
      const run: ChartRun = matchesChartProfile(response, chartProfile)
        ? { status: "success", result: response, snapshotId: snapshot }
        : { status: "error", issue: "profileChanged" };
      setChartState({ ...context, run });
    } catch (error: unknown) {
      if (!request.signal.aborted) {
        setChartState({ ...context, run: { status: "error", issue: getChartIssue(error) } });
      }
    } finally {
      if (chartRequestRef.current === request) chartRequestRef.current = null;
    }
  }

  const getLiveContextForCoordinator = useCallback((): {
    status: AuthSessionStatus;
    ownerKey: string | null;
  } | null => {
    if (hasExplicitTokenProp || !session) {
      return null;
    }
    const snap = session.getSnapshot();
    return {
      status: snap.status,
      ownerKey: snap.status === "authenticated" ? (snap.user?.id ?? "session-user") : null,
    };
  }, [hasExplicitTokenProp, session]);

  const handleAuthFailure = useCallback((): "unavailable" | "unauthenticated" => {
    if (!hasExplicitTokenProp && session) {
      const live = session.getSnapshot();
      if (live.status === "unavailable") {
        // Keep loaded profiles, selection, staged settings, and unsaved form input
        // intact while the authentication service recovers.
        return "unavailable";
      }
    }
    profileLoadCoordinator.invalidate();
    if (hasExplicitTokenProp || !session) {
      setLocalAuthStatus("unauthenticated");
    }
    setProfileState((prev) => applySessionCleared(prev));
    setConfirmDeleteId(null);
    setFormMode("closed");
    return "unauthenticated";
  }, [hasExplicitTokenProp, profileLoadCoordinator, session]);

  const executeProfileListFetch = useCallback(
    (ownerKey: string): Promise<BirthProfile[] | null> => {
      return profileLoadCoordinator.startLoad({
        ownerKey,
        getAccessToken: effectiveGetAccessToken,
        unavailableFallbackMessage: t.sessionUnavailableBannerBody,
        getLiveContext: getLiveContextForCoordinator,
        fetchList: async (validToken) => {
          if (hasExplicitTokenProp || !session) {
            setLocalAuthStatus("authenticated");
          }
          const response = await listProfiles({
            getAccessToken: () => validToken,
            onUnauthorizedRefresh: effectiveOnUnauthorizedRefresh,
            baseUrl: apiBaseUrl,
          });
          return response.items;
        },
        onLoadingChange: (isLoading) => {
          setIsLoadingProfiles(isLoading);
          if (isLoading) {
            setApiErrorBanner(null);
          }
        },
        onLoaded: (items) => {
          setProfileState((prev) => applyLoadedProfiles(prev, items));
          setApiErrorBanner(null);
          setSessionFeedback(null);
        },
        onUnauthenticated: () => {
          handleAuthFailure();
        },
        onUnavailable: () => {
          if (hasExplicitTokenProp || !session) {
            setLocalAuthStatus((prev) => (prev === "checking" ? "unavailable" : prev));
          }
          setApiErrorBanner(t.profileLoadFailed);
        },
        onError: () => {
          if (hasExplicitTokenProp || !session) {
            setLocalAuthStatus((prev) => (prev === "checking" ? "unavailable" : prev));
          }
          setApiErrorBanner(t.profileLoadFailed);
        },
      });
    },
    [
      apiBaseUrl,
      effectiveGetAccessToken,
      effectiveOnUnauthorizedRefresh,
      getLiveContextForCoordinator,
      handleAuthFailure,
      hasExplicitTokenProp,
      profileLoadCoordinator,
      session,
      t.profileLoadFailed,
      t.sessionUnavailableBannerBody,
    ]
  );

  const loadSavedProfilesFromApi = useCallback(async () => {
    const ownerKey =
      !hasExplicitTokenProp && session
        ? (session.user?.id ?? "session-user")
        : `prop-session-${explicitProviderSeqRef.current}`;
    return executeProfileListFetch(ownerKey);
  }, [executeProfileListFetch, hasExplicitTokenProp, session]);

  useEffect(() => {
    let active = true;

    if (hasExplicitTokenProp) {
      if (prevExplicitTokenProviderRef.current !== getAccessToken) {
        prevExplicitTokenProviderRef.current = getAccessToken;
        explicitProviderSeqRef.current += 1;
      }
      const propOwnerKey = `prop-session-${explicitProviderSeqRef.current}`;
      profileLoadCoordinator.syncSessionContext({
        status: "checking",
        ownerKey: propOwnerKey,
      });
      void executeProfileListFetch(propOwnerKey);
      return () => {
        active = false;
      };
    }

    if (!session) {
      return () => {
        active = false;
      };
    }

    const sessionOwnerKey =
      session.status === "authenticated" ? (session.user?.id ?? "session-user") : null;
    const transition = profileLoadCoordinator.syncSessionContext({
      status: session.status,
      ownerKey: sessionOwnerKey,
    });

    if (transition.shouldClearWorkspace) {
      void Promise.resolve().then(() => {
        if (!active) return;
        setProfileState((prev) =>
          prev.savedProfiles.length > 0 ? applySessionCleared(prev) : prev
        );
        setConfirmDeleteId(null);
        setProfileActionNotice(null);
        setFormServerErrors([]);
        setFormMode("closed");
        if (session.status === "unauthenticated") {
          setIsLoadingProfiles(false);
        }
      });
    }

    if (transition.shouldFetch && sessionOwnerKey) {
      void executeProfileListFetch(sessionOwnerKey);
    }

    return () => {
      active = false;
    };
  }, [
    executeProfileListFetch,
    getAccessToken,
    hasExplicitTokenProp,
    profileLoadCoordinator,
    session,
  ]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        const accountMenu = accountMenuRef.current;
        if (accountMenu?.open) {
          accountMenu.open = false;
          accountMenu.querySelector("summary")?.focus();
          return;
        }
        setSettingsOpen(false);
        setHighlightedFactId(null);
        setConfirmDeleteId(null);
        setShowLogoutAllConfirm(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (showLogoutAllConfirm) logoutCancelRef.current?.focus();
  }, [showLogoutAllConfirm]);

  function closeLogoutConfirmation() {
    setShowLogoutAllConfirm(false);
    accountMenuRef.current?.querySelector("summary")?.focus();
  }

  function openPage(section: WorkspacePage) {
    setPage(section);
    setNavigationOpen(false);
    setSettingsOpen(false);
    setConfirmDeleteId(null);
    workspaceMainRef.current?.focus();
  }

  function handleLoadSample() {
    setPage("chart");
    setProfileState((prev) => activateSyntheticSamplePreview(prev));
    setAppliedSettings(DEFAULT_SETTINGS);
    setStagedSettings(DEFAULT_SETTINGS);
    setShowDashaNotice(false);
    setProfileActionNotice(null);
    setApiErrorBanner(null);
    setFormServerErrors([]);
    setConfirmDeleteId(null);
    setFormMode("closed");
    setHighlightedFactId(null);
  }

  function handleOpenCreateForm() {
    if (!isAuthenticated) return;
    setFormServerErrors([]);
    setApiErrorBanner(null);
    setProfileActionNotice(null);
    setConfirmDeleteId(null);
    setFormMode("create");
  }

  function handleOpenEditForm() {
    if (!isAuthenticated || !activeProfile || activeProfile.is_synthetic_sample) return;
    setFormServerErrors([]);
    setApiErrorBanner(null);
    setProfileActionNotice(null);
    setConfirmDeleteId(null);
    setFormMode("edit");
  }

  async function handleRetrySession() {
    if (!hasExplicitTokenProp && session) {
      setApiErrorBanner(null);
      const nextSnapshot = await session.retrySession();
      if (nextSnapshot.status === "authenticated" && nextSnapshot.user) {
        await executeProfileListFetch(nextSnapshot.user.id);
      }
      return;
    }
    if (effectiveGetAccessToken) {
      const propOwnerKey = `prop-session-${explicitProviderSeqRef.current}`;
      profileLoadCoordinator.syncSessionContext({
        status: "checking",
        ownerKey: propOwnerKey,
      });
      setLocalAuthStatus("checking");
      await executeProfileListFetch(propOwnerKey);
    }
  }

  async function handleSignOut() {
    if (!session || isSigningOut || isSigningOutAll) return;
    setIsSigningOut(true);
    setSessionFeedback(null);
    setShowLogoutAllConfirm(false);
    setApiErrorBanner(null);
    try {
      const result = await session.logout();
      profileLoadCoordinator.invalidate();
      setProfileState((prev) => applySessionCleared(prev));
      setConfirmDeleteId(null);
      setFormMode("closed");
      setFormServerErrors([]);
      setSessionFeedback(classifyLogoutOutcome(result, t));
    } finally {
      setIsSigningOut(false);
    }
  }

  async function handleConfirmLogoutAll() {
    if (!session || isSigningOut || isSigningOutAll) return;
    setIsSigningOutAll(true);
    setSessionFeedback(null);
    setApiErrorBanner(null);
    try {
      const result = await session.logoutAll();
      setShowLogoutAllConfirm(false);
      if (result.ok) {
        profileLoadCoordinator.invalidate();
        setProfileState((prev) => applySessionCleared(prev));
        setConfirmDeleteId(null);
        setFormMode("closed");
        setFormServerErrors([]);
      }
      setSessionFeedback(classifyLogoutAllOutcome(result, t));
    } finally {
      setIsSigningOutAll(false);
    }
  }

  async function handleSubmitProfileForm(payload: BirthProfileCreatePayload) {
    if (!isAuthenticated) return;
    const snap = profileLoadCoordinator.getSnapshot();
    const requestGeneration = snap.generation;
    const requestOwnerKey = snap.ownerKey ?? "";

    setIsSubmittingForm(true);
    setFormServerErrors([]);
    setApiErrorBanner(null);
    setProfileActionNotice(null);

    const clientConfig = {
      getAccessToken: effectiveGetAccessToken,
      onUnauthorizedRefresh: effectiveOnUnauthorizedRefresh,
      baseUrl: apiBaseUrl,
    };

    try {
      if (formMode === "edit" && activeProfile && !activeProfile.is_synthetic_sample) {
        const updated = await updateProfile(clientConfig, activeProfile.id, payload);
        if (
          !profileLoadCoordinator.isCurrentRequest({
            requestGeneration,
            ownerKey: requestOwnerKey,
            getLiveContext: getLiveContextForCoordinator,
          })
        ) {
          return;
        }
        setProfileState((prev) => applyUpdatedProfile(prev, updated));
        setProfileActionNotice("profileUpdatedNotice");
      } else {
        const created = await createProfile(clientConfig, payload);
        if (
          !profileLoadCoordinator.isCurrentRequest({
            requestGeneration,
            ownerKey: requestOwnerKey,
            getLiveContext: getLiveContextForCoordinator,
          })
        ) {
          return;
        }
        setProfileState((prev) => applyCreatedProfile(prev, created));
        setProfileActionNotice("profileCreatedNotice");
      }
      setFormMode("closed");
      setShowDashaNotice(false);
      setHighlightedFactId(null);
    } catch (err) {
      if (profileLoadCoordinator.getSnapshot().generation !== requestGeneration) {
        return;
      }
      if (err instanceof ApiClientError) {
        if (err.status === 422 && isProfileInputIssue(err.responseCode)) {
          setFormServerErrors(err.responseCode);
          return;
        }
        const authClass = classifyWorkspaceAuthError({
          errorCode: err.code,
          liveSessionStatus:
            !hasExplicitTokenProp && session ? session.getSnapshot().status : null,
        });
        if (authClass !== "other") {
          const outcome = handleAuthFailure();
          if (outcome === "unavailable") {
            setFormServerErrors([t.sessionUnavailableBannerBody]);
            return;
          }
        }
      }
      setFormServerErrors([t.profileSaveFailed]);
    } finally {
      setIsSubmittingForm(false);
    }
  }

  async function handleConfirmDeleteProfile(profileId: string) {
    if (!isAuthenticated || profileId === SAMPLE_NORTH_LONDON_PROFILE.id) return;
    const snap = profileLoadCoordinator.getSnapshot();
    const requestGeneration = snap.generation;
    const requestOwnerKey = snap.ownerKey ?? "";

    setIsDeletingProfile(true);
    setApiErrorBanner(null);
    setProfileActionNotice(null);

    try {
      await deleteProfile(
        {
          getAccessToken: effectiveGetAccessToken,
          onUnauthorizedRefresh: effectiveOnUnauthorizedRefresh,
          baseUrl: apiBaseUrl,
        },
        profileId
      );
      if (
        !profileLoadCoordinator.isCurrentRequest({
          requestGeneration,
          ownerKey: requestOwnerKey,
          getLiveContext: getLiveContextForCoordinator,
        })
      ) {
        return;
      }
      setProfileState((prev) => applyDeletedProfile(prev, profileId));
      setConfirmDeleteId(null);
      setProfileActionNotice("profileDeletedNotice");
      setHighlightedFactId(null);
    } catch (err) {
      if (profileLoadCoordinator.getSnapshot().generation !== requestGeneration) {
        return;
      }
      if (err instanceof ApiClientError) {
        const authClass = classifyWorkspaceAuthError({
          errorCode: err.code,
          liveSessionStatus:
            !hasExplicitTokenProp && session ? session.getSnapshot().status : null,
        });
        if (authClass !== "other") {
          const outcome = handleAuthFailure();
          setApiErrorBanner(
            outcome === "unavailable" ? t.sessionUnavailableBannerBody : t.profileDeleteFailed
          );
        } else {
          setApiErrorBanner(t.profileDeleteFailed);
        }
      } else {
        setApiErrorBanner(t.profileDeleteFailed);
      }
      setConfirmDeleteId(null);
    } finally {
      setIsDeletingProfile(false);
    }
  }

  function closeSettings() {
    setSettingsOpen(false);
    settingsTriggerRef.current?.focus();
  }

  function handleApplySettings() {
    const scope = classifySettingsChange(appliedSettings, stagedSettings);
    if (scope === "none") return;
    setAppliedSettings(stagedSettings);
    closeSettings();
    setShowDashaNotice(scope === "dasha_only");
  }

  function handleDiscardSettings() {
    setStagedSettings(appliedSettings);
  }

  const lagna = getLagnaFact(chart);
  const placements = getPlacementFacts(chart);
  const selectedFact =
    highlightedFactId === "f_lagna"
      ? lagna
      : (placements.find((p) => p.id === highlightedFactId) ?? null);

  const provenanceLabel =
    provenanceStatus === "swieph"
      ? t.provenanceSwieph
      : provenanceStatus === "moshier"
        ? t.provenanceMoshier
        : provenanceStatus === "mixed"
          ? t.provenanceMixed
          : t.provenanceUnknown;

  const hasEphemerisFallback = provenanceStatus === "moshier" || provenanceStatus === "mixed";
  const provenanceClasses =
    provenanceStatus === "swieph"
      ? "border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] text-[var(--kundali-emerald)]"
      : hasEphemerisFallback
        ? "border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] text-[var(--kundali-ink)]"
        : "border-[var(--kundali-slate-border)] bg-[var(--kundali-slate-bg)] text-[var(--kundali-ink)]";

  const profileIssue: ChartIssue | null = chartProfile
    ? chartProfile.bs_conversion_status === "awaiting_bs_conversion" ||
      (chartProfile.input_calendar === "BS" && !chartProfile.date_ad)
      ? "bsPending"
      : !chartProfile.date_ad || !chartProfile.timezone ||
          (chartProfile.time_certainty !== "unknown" && !chartProfile.time_local)
          ? "incomplete"
          : null
    : null;
  const chartIssue = chartRun.status === "error" ? chartRun.issue : profileIssue;
  const shouldReloadProfiles = chartIssue === "profileChanged" || chartIssue === "missing";
  const canRetryChart = chartIssue === "network" || chartIssue === "server";
  const isCalculating = chartRun.status === "loading";

  async function handleReloadChartProfiles() {
    const loaded = await loadSavedProfilesFromApi();
    if (loaded) {
      setChartState((current) => current === chartState
        ? { ...current, run: { status: "idle" } }
        : current);
    }
  }

  const showForm = formMode !== "closed";
  const effectiveFormMode: "create" | "edit" =
    formMode === "edit" && activeProfile && !activeProfile.is_synthetic_sample ? "edit" : "create";
  const editingTarget = effectiveFormMode === "edit" ? activeProfile : null;

  const profileFields = (
    <>
      {profileChoices.length > 0 ? (
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
          <label htmlFor="active-profile-select" className="sr-only">
            {t.profileLabel}
          </label>
          <select
            id="active-profile-select"
            value={summaryProfile?.id ?? ""}
            onChange={(e) => {
              const nextId = e.target.value;
              setProfileState((prev) => ({ ...prev, activeProfileId: nextId }));
              setFormMode("closed");
              setConfirmDeleteId(null);
              setFormServerErrors([]);
              setHighlightedFactId(null);
            }}
            className="min-w-0 max-w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] min-h-11 px-3 py-2 text-sm font-semibold text-[var(--kundali-navy)] sm:max-w-64"
          >
            {!summaryProfile ? <option value="" disabled>{t.profileLabel}</option> : null}
            {profileChoices.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          {summaryProfile ? (
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--kundali-ink)]">
              <span className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2 py-0.5 font-mono tabular-data">
                {t.enteredInPrefix} {summaryProfile.input_calendar}:{" "}
                {summaryProfile.entered_date}
                {summaryProfile.time_local ? ` · ${summaryProfile.time_local}` : ""}
              </span>
              {summaryProfile.input_calendar === "BS" && summaryProfile.date_ad ? (
                <span className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2 py-0.5">
                  {t.convertedAdLabel} <time dateTime={summaryProfile.date_ad} className="font-mono">{summaryProfile.date_ad}</time>
                </span>
              ) : null}
              <span className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2 py-0.5 [overflow-wrap:anywhere]">
                {summaryProfile.place_name}
              </span>
              <span className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2 py-0.5 font-mono">
                {summaryProfile.timezone}
              </span>
              <span
                className={`rounded border px-2 py-0.5 font-medium ${
                  summaryProfile.time_certainty === "exact"
                    ? "border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] text-[var(--kundali-emerald)]"
                    : summaryProfile.time_certainty === "approximate"
                    ? "border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] text-[var(--kundali-ink)]"
                      : "border-[var(--kundali-slate-border)] bg-[var(--kundali-slate-bg)] text-[var(--kundali-ink)]"
                }`}
              >
                {summaryProfile.time_certainty === "exact"
                  ? t.timeExact
                  : summaryProfile.time_certainty === "approximate"
                    ? t.timeApproximate
                    : t.timeUnknown}
              </span>
              {!summaryProfile.is_synthetic_sample &&
              summaryProfile.bs_conversion_status === "awaiting_bs_conversion" ? (
                <span className="rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] px-2 py-0.5 font-medium text-[var(--kundali-ink)]">
                  {t.savedProfileBsStatusBadge}
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </>
  );
  const settingsButton = (
    <div className="relative min-w-0">
      <button
        ref={settingsTriggerRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={settingsOpen}
        onClick={() => {
          setStagedSettings(appliedSettings);
          setSettingsOpen((v) => !v);
        }}
        className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] min-h-11 px-3 py-2 text-sm font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-strip)]"
      >
        {t.settingsButton}
      </button>

      <CalculationSettingsPopover
        open={settingsOpen}
        moonOnly={page === "chart" && unknownTimeMode}
        align={page === "settings" ? "start" : "end"}
        locale={locale}
        appliedSettings={appliedSettings}
        stagedSettings={stagedSettings}
        onStageChange={setStagedSettings}
        onDiscard={handleDiscardSettings}
        onApply={handleApplySettings}
        onClose={closeSettings}
        labels={{
          title: t.settingsTitle,
          presetLabel: t.presetLabel,
          presetStandard: t.presetStandard,
          presetHamro: t.presetHamro,
          ayanamshaLabel: t.ayanamshaLabel,
          nodeTypeLabel: t.nodeTypeLabel,
          houseSystemLabel: t.houseSystemLabel,
          houseSystemFixedValue: t.houseSystemFixedValue,
          yearDaysLabel: t.yearDaysLabel,
          scopeNone: t.scopeNone,
          scopeDashaOnly: t.scopeDashaOnly,
          scopeFullChart: t.scopeFullChart,
          discard: t.discard,
          applySettings: t.applySettings,
          close: t.close,
        }}
      />
    </div>
  );
  const languageLabel = locale === "ne" ? "labelNe" : "labelEn";
  const ayanamsha = AYANAMSHA_OPTIONS.find(({ value }) => value === (moon?.ayanamsha ?? resolvedSettings.ayanamsha));
  const nodeType = NODE_TYPE_OPTIONS.find(({ value }) => value === resolvedSettings.node_type);
  const yearLength = YEAR_DAYS_OPTIONS.find(({ value }) => value === resolvedSettings.year_days);
  const conventions = (
    <span className="min-w-0 text-xs leading-relaxed text-[var(--kundali-muted)]">
      {ayanamsha?.[languageLabel]}
      {!(page === "chart" && unknownTimeMode) && <> · {nodeType?.[languageLabel]} · {t.houseSystemFixedValue}</>}
    </span>
  );

  return (
    <div lang={locale} className="flex min-h-screen flex-col bg-[var(--kundali-cream)] text-[var(--kundali-ink)]">
      <a href="#workspace-main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:bg-white focus:px-3 focus:py-2">
        {t.skipToWorkspace}
      </a>
      <header className="relative z-30 bg-[var(--kundali-navy)] px-3 text-white sm:px-6">
        <div className="mx-auto flex min-h-16 max-w-[1600px] items-center justify-between gap-2">
          <Link href="/" className="inline-flex min-h-11 items-center gap-2">
            <svg width="27" height="27" viewBox="0 0 36 36" fill="none" stroke="currentColor" aria-hidden="true">
              <circle cx="18" cy="18" r="15" />
              <path d="M18 3 33 18 18 33 3 18Z M10 10l16 16m0-16L10 26" />
              <circle cx="18" cy="18" r="4" />
            </svg>
            <span className="font-serif text-xl font-semibold">{t.brandName}</span>
            <span lang="ne" className="hidden text-xs text-white/85 sm:inline">{t.brandNative}</span>
          </Link>
          <div className="flex min-w-0 items-center gap-2 sm:gap-4">
            <div role="group" aria-label={t.localeLabel} className="flex rounded border border-white/35">
              {(["en", "ne"] as const).map((language) => (
                <button key={language} type="button" lang={language} aria-pressed={locale === language}
                  onClick={() => setLocale(language)}
                  className={`min-h-11 px-2 text-xs font-semibold sm:px-3 ${locale === language ? "bg-[var(--kundali-cream)] text-[var(--kundali-navy)]" : "hover:bg-white/10"}`}>
                  {language === "en" ? "EN" : "नेपाली"}
                </button>
              ))}
            </div>
            {session?.user || (session && isAuthenticated) ? (
              <details ref={accountMenuRef} className="group/account relative" onBlur={(event) => {
                if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) {
                  event.currentTarget.open = false;
                }
              }}>
                <summary className="flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded border border-white/35 px-2 text-xs font-semibold hover:bg-white/10 sm:px-3 [&::-webkit-details-marker]:hidden">
                  {t.accountMenu}<span aria-hidden="true">⌄</span>
                </summary>
                <div className="absolute right-0 top-full mt-2 hidden w-64 max-w-[calc(100vw-2rem)] rounded border border-[var(--kundali-border)] bg-white p-2 text-[var(--kundali-ink)] shadow-lg group-open/account:block">
                  {session.user ? (
                    <div className="border-b border-[var(--kundali-border-subtle)] px-2 pb-2 text-xs leading-relaxed">
                      <p className="font-semibold [overflow-wrap:anywhere]">{session.user.email}</p>
                      <p className="text-[var(--kundali-muted)]">{t.signedInRolePrefix} {session.user.role}</p>
                    </div>
                  ) : null}
                  <button type="button" disabled={isSigningOut || isSigningOutAll}
                    onClick={() => void handleSignOut()}
                    className="min-h-11 w-full rounded px-2 text-start text-sm font-semibold hover:bg-[var(--kundali-strip)] disabled:opacity-60">
                    {isSigningOut ? t.signingOutButton : t.signOutButton}
                  </button>
                  <button type="button" disabled={isSigningOut || isSigningOutAll}
                    onClick={() => {
                      if (accountMenuRef.current) accountMenuRef.current.open = false;
                      setShowLogoutAllConfirm(true);
                      setSessionFeedback(null);
                    }}
                    className="min-h-11 w-full rounded px-2 text-start text-sm font-semibold text-[var(--kundali-crimson)] hover:bg-[var(--kundali-crimson-bg)] disabled:opacity-60">
                    {isSigningOutAll ? t.signingOutAllButton : t.signOutAllButton}
                  </button>
                </div>
              </details>
            ) : null}
          </div>
        </div>
      </header>

      <div className="mx-auto grid w-full max-w-[1600px] flex-1 grid-rows-[auto_1fr] lg:grid-cols-[208px_minmax(0,1fr)] lg:grid-rows-1 xl:grid-cols-[232px_minmax(0,1fr)]">
        <aside className="border-b border-[var(--kundali-border)] bg-[var(--kundali-strip)] px-4 py-2.5 lg:border-r lg:border-b-0 lg:px-4 lg:py-8 xl:px-5">
          <button type="button" aria-expanded={navigationOpen} aria-controls="workspace-navigation"
            onClick={() => setNavigationOpen((open) => !open)}
            className="flex min-h-11 w-full items-center justify-between rounded border border-[var(--kundali-border)] bg-[var(--kundali-cream)] px-3 text-sm font-semibold text-[var(--kundali-navy)] lg:hidden">
            {t.navigationToggle}<span aria-hidden="true">{navigationOpen ? "−" : "+"}</span>
          </button>
          <div id="workspace-navigation" className={navigationOpen ? "mt-3" : "hidden lg:block"}>
            <nav aria-label={t.workspaceNavigation} className="space-y-1">
              {(["chart", "profiles", "settings"] as const).map((section) => (
                <button key={section} type="button" aria-current={page === section ? "page" : undefined}
                  onClick={() => openPage(section)}
                  className={`block min-h-11 w-full rounded border px-3 py-2 text-start text-sm font-semibold ${page === section ? "border-[var(--kundali-border)] bg-white text-[var(--kundali-navy)]" : "border-transparent hover:bg-[var(--kundali-cream)]"}`}>
                  {pageLabels[section].title}
                </button>
              ))}
            </nav>
            <div className="mt-7 border-t border-[var(--kundali-border)] px-3 pt-5 text-sm text-[var(--kundali-muted)]">
              <p className="font-semibold text-[var(--kundali-navy)]">{t.plannedHeading}</p>
              <ul className="mt-2 space-y-2 leading-relaxed">
                {[t.plannedTransits, t.plannedAi, t.plannedCompatibility].map((label) => <li key={label}>{label}</li>)}
              </ul>
            </div>
          </div>
        </aside>

        <main ref={workspaceMainRef} id="workspace-main" tabIndex={-1} className="min-w-0 px-4 pt-6 pb-10 sm:px-6 sm:pt-8 xl:px-8">
          <div className="mb-5 border-b border-[var(--kundali-border)] pb-4 sm:mb-6">
            <h1 className={`text-3xl leading-tight font-normal text-[var(--kundali-navy)] sm:text-[2.65rem] ${locale === "en" ? "font-serif tracking-tight" : "leading-[1.25]"}`}>
              {pageLabels[page].title}
            </h1>
            <p className="mt-1.5 text-sm leading-relaxed text-[var(--kundali-muted)]">{pageLabels[page].description}</p>
          </div>
          {sessionFeedback ? (
            <div
              role={sessionFeedback.tone === "crimson" ? "alert" : "status"}
              className={`mb-4 rounded border px-4 py-2.5 text-xs font-medium ${
                sessionFeedback.tone === "emerald"
                  ? "border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] text-[var(--kundali-emerald)]"
                  : sessionFeedback.tone === "amber"
                    ? "border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] text-[var(--kundali-amber)]"
                    : "border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] text-[var(--kundali-crimson)]"
              }`}
            >
              {sessionFeedback.message}
            </div>
          ) : null}

          {showLogoutAllConfirm ? (
            <div
              role="alertdialog"
              aria-label={t.logoutConfirmTitle}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.stopPropagation();
                  closeLogoutConfirmation();
                }
              }}
              className="mb-4 rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-4 py-3 text-xs"
            >
              <p className="font-semibold text-[var(--kundali-crimson)]">{t.logoutConfirmTitle}</p>
              <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">{t.logoutConfirmBody}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={isSigningOutAll}
                  onClick={() => void handleConfirmLogoutAll()}
                  className="inline-flex min-h-11 items-center rounded bg-[var(--kundali-crimson)] px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSigningOutAll ? t.signingOutAllButton : t.logoutConfirmProceed}
                </button>
                <button
                  type="button"
                  ref={logoutCancelRef}
                  disabled={isSigningOutAll}
                  onClick={closeLogoutConfirmation}
                  className="inline-flex min-h-11 items-center rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--kundali-ink)]"
                >
                  {t.logoutConfirmCancel}
                </button>
              </div>
            </div>
          ) : null}

          {authStatus === "unauthenticated" ? (
            <div
              role="status"
              className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] px-4 py-3 text-xs"
            >
              <div>
                <p className="font-semibold text-[var(--kundali-amber)]">
                  {t.authRequiredBannerTitle}
                </p>
                <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">
                  {t.authRequiredBannerBody}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  href="/login"
                  className="inline-flex min-h-[36px] items-center rounded bg-[var(--kundali-navy)] px-3 py-1.5 text-xs font-semibold text-[var(--kundali-cream)] hover:bg-[var(--kundali-navy-hover)]"
                >
                  {t.signInNavButton}
                </Link>
                <Link
                  href="/register"
                  className="inline-flex min-h-[36px] items-center rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-cream)]"
                >
                  {t.createAccountNavButton}
                </Link>
              </div>
            </div>
          ) : null}

          {authStatus === "unavailable" ? (
            <div
              role="alert"
              className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-4 py-3 text-xs"
            >
              <div>
                <p className="font-semibold text-[var(--kundali-crimson)]">
                  {t.sessionUnavailableBannerTitle}
                </p>
                <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">
                  {t.sessionUnavailableBannerBody}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void handleRetrySession()}
                className="rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--kundali-crimson)]"
              >
                {t.retrySessionButton}
              </button>
            </div>
          ) : null}

          {isLoadingProfiles ? (
            <div role="status" className="mb-4 rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-4 py-3 text-sm font-medium text-[var(--kundali-muted)]">
              {t.loadingProfilesNotice}
            </div>
          ) : null}

          {apiErrorBanner ? (
            <div
              role="alert"
              className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-4 py-2.5 text-xs font-medium text-[var(--kundali-crimson)]"
            >
              <span>{apiErrorBanner}</span>
              {isAuthenticated ? (
                <button
                  type="button"
                  onClick={() => void loadSavedProfilesFromApi()}
                  className="rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--kundali-crimson)]"
                >
                  {t.retryLoadButton}
                </button>
              ) : null}
            </div>
          ) : null}

          {profileActionNotice ? (
            <div
              role="status"
              className="mb-4 rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-4 py-2.5 text-xs font-medium text-[var(--kundali-emerald)]"
            >
              {t[profileActionNotice]}
            </div>
          ) : null}

          {confirmDeleteId && activeProfile && confirmDeleteId === activeProfile.id ? (
            <div
              role="alertdialog"
              aria-label={t.deleteProfileButton}
              className="mb-4 rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-4 py-3 text-xs"
            >
              <p className="font-semibold text-[var(--kundali-crimson)] [overflow-wrap:anywhere]">
                {activeProfile.label} — {t.deleteConfirmPrompt}
              </p>
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={isDeletingProfile}
                  onClick={() => void handleConfirmDeleteProfile(activeProfile.id)}
                  className="rounded bg-[var(--kundali-crimson)] px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isDeletingProfile ? t.formDeleting : t.deleteConfirmButton}
                </button>
                <button
                  type="button"
                  disabled={isDeletingProfile}
                  onClick={() => setConfirmDeleteId(null)}
                  className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--kundali-ink)]"
                >
                  {t.deleteCancelButton}
                </button>
              </div>
            </div>
          ) : null}

          {page === "settings" && displayCalendar !== "AD" ? (
            <div className="mb-4 rounded border border-[var(--kundali-slate-border)] bg-[var(--kundali-slate-bg)]/45 px-3.5 py-2 text-xs text-[var(--kundali-ink)]">
              {t.bsDisplayPending}
            </div>
          ) : null}

          {showDashaNotice ? (
            <div className="mb-4 rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-3.5 py-2 text-xs font-medium text-[var(--kundali-emerald)]">
              {t.dashaOnlyNotice}
            </div>
          ) : null}


          {authStatus === "checking" ? <p role="status" className="py-4 text-sm">{t.sessionCheckingHeaderLabel}</p> : null}
          {page === "profiles" ? (
            <div className="space-y-4">
              {isAuthenticated ? (
                <section aria-label={t.profileLabel} className="space-y-4 rounded border border-[var(--kundali-border)] bg-white p-4 sm:p-5">
                  {profileFields}
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={!isAuthenticated}
                      onClick={handleOpenCreateForm}
                      className="rounded border border-[var(--kundali-navy)] bg-[var(--kundali-surface)] min-h-11 px-3 py-2 text-sm font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-cream)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      + {t.newProfileButton}
                    </button>

                    {activeProfile && !activeProfile.is_synthetic_sample ? (
                      <>
                        <button
                          type="button"
                          disabled={!isAuthenticated || isDeletingProfile}
                          onClick={handleOpenEditForm}
                          className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] min-h-11 px-3 py-2 text-sm font-semibold text-[var(--kundali-ink)] hover:bg-[var(--kundali-cream)] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {t.editProfileButton}
                        </button>
                        <button
                          type="button"
                          disabled={!isAuthenticated || isDeletingProfile}
                          onClick={() => setConfirmDeleteId(activeProfile.id)}
                          className="rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] min-h-11 px-3 py-2 text-sm font-semibold text-[var(--kundali-crimson)] hover:bg-[var(--kundali-crimson-bg)]/80 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {t.deleteProfileButton}
                        </button>
                      </>
                    ) : null}
                  </div>
                </section>
              ) : null}
              {showForm ? (
                <div className="[&_button]:min-h-11 [&_input]:min-h-11 [&_select]:min-h-11">
                  <BirthProfileForm
                    key={editingTarget ? `edit-${editingTarget.id}` : "create-profile"}
                    mode={effectiveFormMode}
                    initialProfile={editingTarget}
                    canCancel
                    isAuthenticated={isAuthenticated}
                    isSubmitting={isSubmittingForm}
                    serverErrors={formServerErrors}
                    locale={locale}
                    searchConfig={{
                      getAccessToken: effectiveGetAccessToken,
                      onUnauthorizedRefresh: effectiveOnUnauthorizedRefresh,
                      baseUrl: apiBaseUrl,
                    }}
                    onInputChange={() => {
                      setFormServerErrors((errors) => typeof errors === "string" ? [] : errors);
                    }}
                    onSubmitProfile={handleSubmitProfileForm}
                    onLoadSyntheticSample={handleLoadSample}
                    onCancel={() => {
                      setFormMode("closed");
                      setFormServerErrors([]);
                    }}
                    labels={{
                      formTitle: t.formTitle,
                      editFormTitle: t.editFormTitle,
                      formSubtitle: t.formSubtitle,
                      authFormLockedNotice: t.authFormLockedNotice,
                      formLabel: t.formLabel,
                      formLabelPlaceholder: t.formLabelPlaceholder,
                      formInputCalendar: t.formInputCalendar,
                      formDate: t.formDate,
                      formDateHint: t.formDateHint,
                      formBsRange: t.formBsRange,
                      formDateErrors: t.formDateErrors,
                      formTimeErrors: t.formTimeErrors,
                      formLocation: t.formLocation,
                      formCertainty: t.formCertainty,
                      formTime: t.formTime,
                      formTimeUnknownNote: t.formTimeUnknownNote,
                      formPlace: t.formPlace,
                      formPlacePlaceholder: t.formPlacePlaceholder,
                      formTimezone: t.formTimezone,
                      formTimezonePlaceholder: t.formTimezonePlaceholder,
                      formLatitude: t.formLatitude,
                      formLongitude: t.formLongitude,
                      formLatitudePlaceholder: t.formLatitudePlaceholder,
                      formLongitudePlaceholder: t.formLongitudePlaceholder,
                      formCoordinatesNote: t.formCoordinatesNote,
                      formSubmit: t.formSubmit,
                      editFormSubmit: t.editFormSubmit,
                      formSaving: t.formSaving,
                      formCancel: t.formCancel,
                      loadSampleButton: t.loadSampleButton,
                      timeExact: t.timeExact,
                      timeApproximate: t.timeApproximate,
                      timeUnknown: t.timeUnknown,
                    }}
                  />
                </div>

              ) : null}
            </div>
          ) : page === "settings" ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <section className="min-w-0 rounded border border-[var(--kundali-border)] bg-white p-4 sm:p-5">
                <h2 className="mb-3 text-lg font-semibold text-[var(--kundali-navy)]">{t.settingsTitle}</h2>
                <div className="mb-4 flex flex-wrap items-center gap-3">{settingsButton}{conventions}</div>
                  <div
                    className="inline-flex items-center overflow-hidden rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] text-[11px]"
                    role="group"
                    aria-label={t.displayCalendarLabel}
                  >
                    <span className="border-r border-[var(--kundali-border-subtle)] bg-[var(--kundali-cream)] px-2 py-1 font-medium text-[var(--kundali-muted)]">
                      {t.displayCalendarLabel}
                    </span>
                    {(
                      [
                        { id: "AD", label: t.displayAd },
                        { id: "BS", label: t.displayBs },
                        { id: "BOTH", label: t.displayBoth },
                      ] as const
                    ).map((opt) => (
                      <button
                        key={opt.id}
                        type="button"
                        aria-pressed={displayCalendar === opt.id}
                        onClick={() => setDisplayCalendar(opt.id)}
                        className={`min-h-11 px-2 font-semibold ${
                          displayCalendar === opt.id
                            ? "bg-[var(--kundali-navy)] text-[var(--kundali-cream)]"
                            : "text-[var(--kundali-ink)] hover:bg-[var(--kundali-strip)]"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
              </section>
              <section className="rounded border border-[var(--kundali-border)] bg-white p-4 sm:p-5">
                <h2 className="mb-2 text-lg font-semibold text-[var(--kundali-navy)]">{t.privacyHeading}</h2>
                <p className="text-sm leading-relaxed text-[var(--kundali-muted)]">{t.privacyBody}</p>
              </section>
            </div>
          ) : activeProfile ? (
            <div className="space-y-4">
              <section aria-label={t.profileLabel} className="space-y-3 rounded border border-[var(--kundali-border)] bg-[var(--kundali-strip)] p-4">
                <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1 basis-72">{profileFields}</div>
                  {settingsButton}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--kundali-border)] pt-3">
                  {conventions}
                  {chart || moon?.ephemeris_source ? <span className={`rounded border px-2 py-1 text-xs font-semibold ${provenanceClasses}`}>{provenanceLabel}</span> : null}
                </div>
              </section>
              {activeProfile?.is_synthetic_sample ? (
                <div className="rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-4 py-3 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold text-[var(--kundali-emerald)]">
                      {t.sampleBannerTitle}
                    </p>
                    {calcState === "awaiting_recompute" ? (
                      <button
                        type="button"
                        onClick={() => {
                          setAppliedSettings(DEFAULT_SETTINGS);
                          setStagedSettings(DEFAULT_SETTINGS);
                          setShowDashaNotice(false);
                        }}
                        className="rounded border border-[var(--kundali-emerald)] bg-[var(--kundali-surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--kundali-emerald)]"
                      >
                        {t.restoreSampleButton}
                      </button>
                    ) : null}
                  </div>
                  <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">
                    {t.sampleBannerBody}
                  </p>
                </div>
              ) : null}

              {chartProfile ? (
                <div className="flex min-h-16 flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-4 py-3 text-sm">
                  <div className="min-w-0 flex-1 basis-40 leading-relaxed">
                    <p role="status" className="font-semibold text-[var(--kundali-navy)]">
                      {isCalculating ? t.calculatingChart : moon ? t.moonWindow.calculated : result ? t.chartCalculated : chartIssue ? "" : t.readyToCalculate}
                    </p>
                    {chartIssue ? (
                      <p role={chartRun.status === "error" ? "alert" : undefined} className="text-[var(--kundali-crimson)]">
                        {t.chartIssues[chartIssue]}
                      </p>
                    ) : null}
                  </div>
                  {chartIssue === "auth" ? (
                    <Link href="/login" className="font-semibold text-[var(--kundali-navy)] underline">
                      {t.signInNavButton}
                    </Link>
                  ) : shouldReloadProfiles ? (
                    <button
                      type="button"
                      disabled={isLoadingProfiles}
                      onClick={() => void handleReloadChartProfiles()}
                      className="rounded border border-[var(--kundali-border)] px-3 py-1.5 font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-strip)]"
                    >
                      {t.reloadChartProfiles}
                    </button>
                  ) : !chartIssue || canRetryChart ? (
                    <button
                      type="button"
                      aria-disabled={isCalculating || isLoadingProfiles}
                      onClick={() => void handleCalculateChart()}
                      className="min-h-11 rounded bg-[var(--kundali-navy)] px-5 py-2 text-sm font-semibold text-[var(--kundali-cream)] hover:bg-[var(--kundali-navy-hover)] aria-disabled:opacity-60"
                    >
                      {canRetryChart ? t.retryChart : unknownTimeMode
                        ? (result ? t.moonWindow.recalculate : t.moonWindow.calculate)
                        : (result ? t.recalculateChart : t.calculateChart)}
                    </button>
                  ) : ["bsPending", "unknownTime", "incomplete", "dateRange", "nonexistentDate"].some((issue) => issue === chartIssue) ? (
                    <button type="button" onClick={() => openPage("profiles")}
                      className="min-h-11 rounded border border-[var(--kundali-border)] px-3 text-sm font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-strip)]">
                      {t.openProfiles}
                    </button>
                  ) : null}
                </div>
              ) : null}

              {activeProfile?.time_certainty === "approximate" ? (
                <div className="rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] px-4 py-3 text-xs">
                  <p className="font-semibold text-[var(--kundali-ink)]">
                    {t.approxBannerTitle}
                  </p>
                  <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">
                    {t.approxBannerBody}
                  </p>
                </div>
              ) : null}

              {sensitivityFact ? (
                <div className="rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] px-4 py-3 text-xs">
                  <p className="font-semibold text-[var(--kundali-ink)]">
                    {t.lagnaSensitivityTitle}
                  </p>
                  <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">
                    {t.lagnaSensitivityBody.replace(
                      "{distance}", sensitivityFact.boundary_distance_degrees.toFixed(2)
                    )}
                  </p>
                </div>
              ) : null}


              {unknownTimeMode ? (
                <MoonWindowPanel result={moon} labels={t.moonWindow} locale={locale} />
              ) : (
              <div className="grid min-w-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(275px,.85fr)_minmax(0,1.5fr)]">
                <section
                  aria-label={t.chartSectionTitle}
                  className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] p-3 sm:p-4"
                >
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-[var(--kundali-border-subtle)] pb-2.5">
                    <h2 className="text-sm font-semibold text-[var(--kundali-navy)]">
                      {t.chartSectionTitle}
                    </h2>
                    <div
                      className="inline-flex overflow-hidden rounded border border-[var(--kundali-border)] text-[11px]"
                      role="group"
                      aria-label={t.chartSectionTitle}
                    >
                      {(["north", "south"] as const).map((style) => (
                        <button
                          key={style}
                          type="button"
                          aria-pressed={chartStyle === style}
                          onClick={() => setChartStyle(style)}
                          className={`min-h-11 px-2.5 py-1 font-semibold ${
                            chartStyle === style
                              ? "bg-[var(--kundali-navy)] text-[var(--kundali-cream)]"
                              : "bg-[var(--kundali-surface)] text-[var(--kundali-muted)] hover:bg-[var(--kundali-strip)]"
                          }`}
                        >
                          {style === "north" ? t.northLabel : t.southLabel}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="flex justify-center" aria-busy={isCalculating}>
                    {isCalculating ? <KundaliChartPlaceholder chartStyle={chartStyle} loading /> : (
                      <KundaliSvgChart
                        chart={chart}
                        chartStyle={chartStyle}
                        locale={locale}
                        unknownTimeMode={unknownTimeMode}
                        unavailableReason={calcState === "awaiting_recompute" ? t.awaitingRecomputeBody : null}
                        highlightedFactId={highlightedFactId}
                        onSelectFact={setHighlightedFactId}
                        labels={{
                          chartTitle: t.chartSectionTitle,
                          northLabel: t.northLabel,
                          southLabel: t.southLabel,
                          unknownTimeNoticeTitle: t.unknownTimeBannerTitle,
                          unknownTimeNoticeBody: t.unknownTimeBannerBody,
                          unavailableTitle: t.chartEmpty,
                          houseWord: t.houseWord,
                          lagnaShort: t.lagnaShort,
                        }}
                      />
                    )}
                  </div>

                  {selectedFact ? (
                    <div className="mt-3 flex items-center justify-between gap-2 rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-3 py-2 text-xs">
                      <div className="min-w-0">
                        <span className="font-semibold text-[var(--kundali-emerald)]">
                          {t.selectedFactLabel}:{" "}
                        </span>
                        <span className="font-mono text-[11px]">{selectedFact.id}</span>{" "}
                        <span>
                          {selectedFact.type === "lagna"
                            ? `${t.lagnaName} — ${
                                locale === "ne"
                                  ? ZODIAC_SIGNS[selectedFact.sign_index]?.ne
                                  : selectedFact.sign
                              } ${formatDegreeInSign(selectedFact.degree)}`
                            : `${
                                locale === "ne"
                                  ? (PLANET_LABELS[selectedFact.planet]?.ne ??
                                    selectedFact.planet)
                                  : selectedFact.planet
                              } — ${
                                locale === "ne"
                                  ? ZODIAC_SIGNS[selectedFact.sign_index]?.ne
                                  : selectedFact.sign
                              } ${formatDegreeInSign(selectedFact.degree)} (${t.houseWord} ${
                                selectedFact.house
                              }, ${
                                locale === "ne"
                                  ? (NAKSHATRA_NE[selectedFact.nakshatra] ??
                                    selectedFact.nakshatra)
                                  : selectedFact.nakshatra
                              } ${selectedFact.pada})`}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setHighlightedFactId(null)}
                        className="shrink-0 rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-surface)] px-2 py-0.5 text-[11px] font-medium text-[var(--kundali-emerald)]"
                      >
                        {t.clearSelection}
                      </button>
                    </div>
                  ) : null}
                </section>

                <section
                  aria-label={t.tableSectionTitle}
                  aria-busy={isCalculating}
                  className="min-w-0 rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] p-4"
                >
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-[var(--kundali-border-subtle)] pb-2.5">
                    <h2 className="text-sm font-semibold text-[var(--kundali-navy)]">
                      {t.tableSectionTitle}
                    </h2>
                  </div>

                  {isCalculating ? <PlanetaryTableSkeleton /> : (
                    <PlanetaryTable
                      chart={chart}
                      locale={locale}
                      unknownTimeMode={unknownTimeMode}
                      highlightedFactId={highlightedFactId}
                      onSelectFact={setHighlightedFactId}
                      labels={{
                        caption: t.tableCaption,
                        colBody: t.colBody,
                        colSign: t.colSign,
                        colDegree: t.colDegree,
                        colHouse: t.colHouse,
                        colNakshatra: t.colNakshatra,
                        colMotion: t.colMotion,
                        colFactId: t.colFactId,
                        retrogradeLabel: t.retrogradeLabel,
                        directLabel: t.directLabel,
                        lagnaName: t.lagnaName,
                        padaWord: t.padaWord,
                        emptyNotice: t.tableEmptyNotice,
                      }}
                    />
                  )}
                </section>
              </div>
              )}
              {chart ? (
                <details key={chart.chart_id} className="rounded border border-[var(--kundali-border)] bg-white px-4">
                  <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-[var(--kundali-navy)] [&::-webkit-details-marker]:hidden">
                    {t.calculateDetails}<span aria-hidden="true">⌄</span>
                  </summary>
                  <dl className="space-y-2 border-t border-[var(--kundali-border-subtle)] py-4 text-sm">
                    <div><dt className="font-semibold">{t.chartIdentifier}</dt><dd className="font-mono text-xs [overflow-wrap:anywhere]">{chart.chart_id}</dd></div>
                    <div><dt className="font-semibold">{t.engineVersionLabel}</dt><dd>{chart.engine_version}</dd></div>
                    <div><dt className="font-semibold">{t.settingsTitle}</dt><dd>{conventions}</dd></div>
                    <div><dt className="font-semibold">{t.yearDaysLabel}</dt><dd>{yearLength?.[languageLabel]}</dd></div>
                  </dl>
                </details>
              ) : null}
              {!activeProfile.is_synthetic_sample && (natal && snapshotId && !dashaNeedsRecalculation ? (
                <DashaTimeline key={snapshotId} snapshotId={snapshotId} chartId={natal.chart_id}
                  locale={locale} labels={t.dasha} config={{
                    getAccessToken: effectiveGetAccessToken,
                    onUnauthorizedRefresh: effectiveOnUnauthorizedRefresh,
                    baseUrl: apiBaseUrl,
                  }} />
              ) : (
                <section aria-label={t.dasha.title} className="rounded border border-[var(--kundali-border)] bg-white p-4">
                  <h2 className="text-lg font-semibold text-[var(--kundali-navy)]">{t.dasha.title}</h2>
                  <p className="mt-2 text-sm text-[var(--kundali-muted)]">
                    {unknownTimeMode ? t.dasha.unknown : dashaNeedsRecalculation ? t.dasha.recalculate
                      : natal ? t.dasha.missingSnapshot : t.dasha.calculate}
                  </p>
                </section>
              ))}
              {!activeProfile.is_synthetic_sample && (
                <button type="button" onClick={handleLoadSample} className="min-h-11 rounded px-2 text-sm font-semibold text-[var(--kundali-navy)] underline underline-offset-4">
                  {t.syntheticPreviewButton}
                </button>
              )}
            </div>
          ) : authStatus !== "checking" && !isLoadingProfiles ? (
            <section className="grid items-center gap-5 rounded border border-[var(--kundali-border)] bg-white px-5 py-7 sm:grid-cols-[minmax(0,1fr)_minmax(8rem,13rem)] sm:px-8 sm:py-8">
              <div>
                <h2 className={`text-2xl leading-tight text-[var(--kundali-navy)] sm:text-3xl ${locale === "en" ? "font-serif" : "font-medium"}`}>{t.emptyWorkspace}</h2>
                <p className="mt-2 max-w-lg text-sm leading-relaxed text-[var(--kundali-muted)]">{t.selectProfileForChart}</p>
                <div className="mt-5 flex flex-wrap items-center gap-3">
                  {isAuthenticated ? (
                    <button type="button" onClick={() => { openPage("profiles"); handleOpenCreateForm(); }}
                      className="min-h-11 rounded bg-[var(--kundali-navy)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--kundali-navy-hover)]">
                      {t.newProfileButton}
                    </button>
                  ) : null}
                  <button type="button" onClick={handleLoadSample}
                    className="min-h-11 rounded border border-[var(--kundali-border)] bg-[var(--kundali-cream)] px-4 py-2 text-sm font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-strip)]">
                    {t.syntheticPreviewButton}
                  </button>
                </div>
              </div>
              <div className="mx-auto w-28 sm:w-full">
                <KundaliChartPlaceholder />
              </div>
            </section>
          ) : null}
        </main>
      </div>
      {/* Unobstructed Persistent Honest-Framing Footer */}
      <footer className="mt-auto border-t border-[var(--kundali-border)] bg-[var(--kundali-strip)] px-4 py-3 text-xs text-[var(--kundali-muted)] sm:px-6">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <p className="leading-relaxed">{t.disclaimer}</p>
          <p className="shrink-0 font-semibold text-[var(--kundali-navy)]">{t.tagline}</p>
        </div>
      </footer>
    </div>
  );
}
