"use client";

import Link from "next/link";
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useOptionalAuthSession } from "@/components/auth/AuthSessionProvider";
import { calculateChart, getChartIssue, matchesChartProfile, type ChartIssue } from "@/lib/api/charts";
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
import { NAKSHATRA_NE, PLANET_LABELS, ZODIAC_SIGNS } from "@/lib/kundali/constants";
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
  resolveActiveProfile,
  resolveVisibleProfiles,
  type ProfileWorkspaceState,
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
  WorkspaceTab,
} from "@/lib/kundali/types";
import { BirthProfileForm } from "./BirthProfileForm";
import { CalculationSettingsPopover } from "./CalculationSettingsPopover";
import { KundaliSvgChart } from "./KundaliSvgChart";
import { PlanetaryTable } from "./PlanetaryTable";
import { SecondaryContractTabs } from "./SecondaryContractTabs";

export interface WorkspaceMessages {
  brandName: string;
  brandNative: string;
  tagline: string;
  disclaimer: string;
  navWorkspace: string;
  navProfiles: string;
  navPrivacy: string;
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
  | { status: "success"; result: ChartCalculationResponse };

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
  const [formServerErrors, setFormServerErrors] = useState<readonly string[]>([]);
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
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("chat");
  const [mobilePane, setMobilePane] = useState<"chart" | "secondary">("chart");
  const [highlightedFactId, setHighlightedFactId] = useState<string | null>(null);

  const [profileLoadCoordinator] = useState(createProfileLoadCoordinator);
  const explicitProviderSeqRef = useRef<number>(1);
  const prevExplicitTokenProviderRef = useRef<AccessTokenProvider | undefined>(getAccessToken);

  const t = messagesByLocale[locale];
  const isAuthenticated = authStatus === "authenticated";
  const displayedProfileState =
    authStatus === "unauthenticated" ? applySessionCleared(profileState) : profileState;
  const visibleProfiles = resolveVisibleProfiles(displayedProfileState);
  const activeProfile = resolveActiveProfile(displayedProfileState);
  const chartProfile = isAuthenticated && activeProfile && !activeProfile.is_synthetic_sample &&
    (hasExplicitTokenProp || activeProfile.owner_id === session?.user?.id)
    ? activeProfile
    : null;
  // Dasha year length does not change placements. A new calculation sends
  // the latest applied year length; a displayed result keeps its own settings.
  const chartContext = chartProfile ? JSON.stringify([
    chartProfile.owner_id, chartProfile.id, chartProfile.updated_at,
    appliedSettings.ayanamsha, appliedSettings.house_system,
    appliedSettings.node_type, appliedSettings.preset,
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
  const chart = result?.chart ?? samplePreview.chart;
  const calcState = result ? "ready" : samplePreview.state;
  const resolvedSettings = chart?.settings ?? appliedSettings;
  const provenanceStatus = getProvenanceStatus(chart, calcState);
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
      const response = await calculateChart({
        getAccessToken: effectiveGetAccessToken,
        onUnauthorizedRefresh: effectiveOnUnauthorizedRefresh,
        baseUrl: apiBaseUrl,
      }, chartProfile, appliedSettings, request.signal);
      if (request.signal.aborted) return;
      const run: ChartRun = matchesChartProfile(response, chartProfile)
        ? { status: "success", result: response }
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
        onUnauthenticated: (message) => {
          handleAuthFailure();
          setApiErrorBanner(message);
        },
        onUnavailable: (message) => {
          if (hasExplicitTokenProp || !session) {
            setLocalAuthStatus((prev) => (prev === "checking" ? "unavailable" : prev));
          }
          setApiErrorBanner(message);
        },
        onError: (message) => {
          if (hasExplicitTokenProp || !session) {
            setLocalAuthStatus((prev) => (prev === "checking" ? "unavailable" : prev));
          }
          setApiErrorBanner(message);
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
        setSettingsOpen(false);
        setHighlightedFactId(null);
        setConfirmDeleteId(null);
        setShowLogoutAllConfirm(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function handleLoadSample() {
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
        setFormServerErrors(
          err.validationMessages.length > 0 ? err.validationMessages : [err.message]
        );
      } else {
        setFormServerErrors(["Unable to save birth profile."]);
      }
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
            outcome === "unavailable" ? t.sessionUnavailableBannerBody : err.message
          );
        } else {
          setApiErrorBanner(err.message);
        }
      } else {
        setApiErrorBanner(
          err instanceof Error ? err.message : "Unable to delete saved birth profile."
        );
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
      : chartProfile.time_certainty === "unknown"
        ? "unknownTime"
        : !chartProfile.date_ad || !chartProfile.time_local || !chartProfile.timezone
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

  const showForm = formMode !== "closed" || !activeProfile;
  const effectiveFormMode: "create" | "edit" =
    formMode === "edit" && activeProfile && !activeProfile.is_synthetic_sample ? "edit" : "create";
  const editingTarget = effectiveFormMode === "edit" ? activeProfile : null;

  return (
    <div lang={locale} className="flex min-h-screen flex-col bg-[var(--kundali-cream)] text-[var(--kundali-ink)]">
      <a href="#workspace-main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:bg-white focus:px-3 focus:py-2">
        {t.skipToWorkspace}
      </a>
      {/* Top Shell Header */}
      <header className="border-b-2 border-[var(--kundali-emerald)] bg-[var(--kundali-navy)] px-4 py-2.5 text-[var(--kundali-cream)] sm:px-6">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-6">
            <div className="flex items-baseline gap-2.5">
              <span className="text-base font-bold tracking-tight">{t.brandName}</span>
              <span className="text-sm font-semibold text-[#D8E2EC]">{t.brandNative}</span>
            </div>
            <nav aria-label="User sections" className="hidden items-center gap-4 text-xs sm:flex">
              <span className="border-b-2 border-[var(--kundali-amber)] pb-0.5 font-semibold text-white">
                {t.navWorkspace}
              </span>
              <button
                type="button"
                disabled={!isAuthenticated}
                onClick={handleOpenCreateForm}
                className="text-[#BCCCDC] hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {t.navProfiles}
              </button>
              <span className="text-[#9FB3C8]" title="Backend privacy endpoints are stubs">
                {t.navPrivacy}
              </span>
            </nav>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 text-xs">
            <span
              className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1 font-mono text-[11px] font-medium ${provenanceClasses}`}
            >
              <svg
                width="10"
                height="10"
                viewBox="0 0 10 10"
                aria-hidden="true"
                className="shrink-0"
              >
                <circle cx="5" cy="5" r="4" fill={hasEphemerisFallback ? "var(--kundali-amber)" : "currentColor"} />
              </svg>
              {provenanceLabel}
            </span>

            <div
              className="inline-flex overflow-hidden rounded border border-[#486581]"
              role="group"
              aria-label={t.localeLabel}
            >
              {(["en", "ne"] as const).map((loc) => (
                <button
                  key={loc}
                  type="button"
                  aria-pressed={locale === loc}
                  onClick={() => setLocale(loc)}
                  className={`px-2.5 py-1 text-xs font-semibold ${
                    locale === loc
                      ? "bg-[#F7F6F1] text-[#13293D]"
                      : "text-[#D8E2EC] hover:bg-[#1D3B56]"
                  }`}
                >
                  {loc === "en" ? "EN" : "नेपाली"}
                </button>
              ))}
            </div>

            {authStatus === "checking" ? (
              <span
                role="status"
                className="rounded border border-[#486581] bg-[#1D3B56] px-2.5 py-1 text-[11px] font-medium text-[#D8E2EC]"
              >
                {t.sessionCheckingHeaderLabel}
              </span>
            ) : null}

            {authStatus === "unauthenticated" ? (
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  href="/login"
                  className="inline-flex min-h-[34px] items-center rounded border border-[#D8E2EC] bg-[#F7F6F1] px-2.5 py-1 text-xs font-semibold text-[#13293D] hover:bg-white"
                >
                  {t.signInNavButton}
                </Link>
                <Link
                  href="/register"
                  className="inline-flex min-h-[34px] items-center rounded border border-[#486581] bg-[#1D3B56] px-2.5 py-1 text-xs font-semibold text-[#F7F6F1] hover:bg-[#24496B]"
                >
                  {t.createAccountNavButton}
                </Link>
              </div>
            ) : null}

            {authStatus === "unavailable" ? (
              <div className="flex flex-wrap items-center gap-2">
                {session?.user ? (
                  <span className="max-w-[180px] truncate rounded border border-[#486581] bg-[#1D3B56] px-2 py-1 text-[11px] text-[#D8E2EC]">
                    {session.user.email}
                  </span>
                ) : null}
                <span className="rounded border border-[#F3C68F] bg-[#3B2610] px-2.5 py-1 text-[11px] font-medium text-[#FEF3E2]">
                  {t.sessionUnavailableHeaderLabel}
                </span>
                <button
                  type="button"
                  onClick={() => void handleRetrySession()}
                  className="inline-flex min-h-[34px] items-center rounded border border-[#D8E2EC] bg-[#F7F6F1] px-2.5 py-1 text-xs font-semibold text-[#13293D] hover:bg-white"
                >
                  {t.retrySessionButton}
                </button>
              </div>
            ) : null}

            {authStatus === "authenticated" ? (
              <div className="flex flex-wrap items-center gap-2">
                {session?.user ? (
                  <span className="inline-flex max-w-full flex-wrap items-center gap-1.5 rounded border border-[#486581] bg-[#1D3B56] px-2.5 py-1 text-[11px] text-[#F7F6F1]">
                    <span className="max-w-[180px] truncate font-medium sm:max-w-[240px]">
                      {session.user.email}
                    </span>
                    <span className="rounded bg-[#13293D] px-1.5 py-0.5 font-mono text-[10px] uppercase text-[#A7D7C2]">
                      {t.signedInRolePrefix} {session.user.role}
                    </span>
                  </span>
                ) : null}
                {session ? (
                  <>
                    <button
                      type="button"
                      disabled={isSigningOut || isSigningOutAll}
                      onClick={() => void handleSignOut()}
                      className="inline-flex min-h-[34px] items-center rounded border border-[#D8E2EC] bg-[#F7F6F1] px-2.5 py-1 text-xs font-semibold text-[#13293D] hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isSigningOut ? t.signingOutButton : t.signOutButton}
                    </button>
                    <button
                      type="button"
                      disabled={isSigningOut || isSigningOutAll}
                      onClick={() => {
                        setShowLogoutAllConfirm(true);
                        setSessionFeedback(null);
                      }}
                      className="inline-flex min-h-[34px] items-center rounded border border-[#FCA5A5] bg-[#4C1717] px-2.5 py-1 text-xs font-semibold text-[#FEF2F2] hover:bg-[#642020] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isSigningOutAll ? t.signingOutAllButton : t.signOutAllButton}
                    </button>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </header>

      {/* Profile & Conventions Strip */}
      <div className="border-b border-[var(--kundali-border)] bg-[var(--kundali-strip)] px-4 py-2.5 sm:px-6">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2.5">
            {visibleProfiles.length > 0 ? (
              <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
                <label htmlFor="active-profile-select" className="sr-only">
                  {t.profileLabel}
                </label>
                <select
                  id="active-profile-select"
                  value={displayedProfileState.activeProfileId ?? ""}
                  onChange={(e) => {
                    const nextId = e.target.value;
                    setProfileState((prev) => ({ ...prev, activeProfileId: nextId }));
                    setFormMode("closed");
                    setConfirmDeleteId(null);
                    setFormServerErrors([]);
                    setHighlightedFactId(null);
                  }}
                  className="min-w-0 max-w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2.5 py-1.5 text-xs font-semibold text-[var(--kundali-navy)] sm:max-w-64"
                >
                  {visibleProfiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
                {activeProfile ? (
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--kundali-ink)]">
                    <span className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2 py-0.5 font-mono tabular-data">
                      {t.enteredInPrefix} {activeProfile.input_calendar}:{" "}
                      {activeProfile.entered_date}
                      {activeProfile.time_local ? ` · ${activeProfile.time_local}` : ""}
                    </span>
                    <span className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2 py-0.5 font-mono">
                      {activeProfile.timezone}
                    </span>
                    <span
                      className={`rounded border px-2 py-0.5 font-medium ${
                        activeProfile.time_certainty === "exact"
                          ? "border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] text-[var(--kundali-emerald)]"
                          : activeProfile.time_certainty === "approximate"
                          ? "border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] text-[var(--kundali-ink)]"
                            : "border-[var(--kundali-slate-border)] bg-[var(--kundali-slate-bg)] text-[var(--kundali-ink)]"
                      }`}
                    >
                      {activeProfile.time_certainty === "exact"
                        ? t.timeExact
                        : activeProfile.time_certainty === "approximate"
                          ? t.timeApproximate
                          : t.timeUnknown}
                    </span>
                    {!activeProfile.is_synthetic_sample &&
                    activeProfile.bs_conversion_status === "awaiting_bs_conversion" ? (
                      <span className="rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] px-2 py-0.5 font-medium text-[var(--kundali-amber)]">
                        {t.savedProfileBsStatusBadge}
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : (
              <span className="font-medium text-[var(--kundali-muted)]">{t.tagline}</span>
            )}

            <button
              type="button"
              disabled={!isAuthenticated}
              onClick={handleOpenCreateForm}
              className="rounded border border-[var(--kundali-navy)] bg-[var(--kundali-surface)] px-2.5 py-1 text-xs font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-cream)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              + {t.newProfileButton}
            </button>

            {activeProfile && !activeProfile.is_synthetic_sample ? (
              <>
                <button
                  type="button"
                  disabled={!isAuthenticated || isDeletingProfile}
                  onClick={handleOpenEditForm}
                  className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2.5 py-1 text-xs font-semibold text-[var(--kundali-ink)] hover:bg-[var(--kundali-cream)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {t.editProfileButton}
                </button>
                <button
                  type="button"
                  disabled={!isAuthenticated || isDeletingProfile}
                  onClick={() => setConfirmDeleteId(activeProfile.id)}
                  className="rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-2.5 py-1 text-xs font-semibold text-[var(--kundali-crimson)] hover:bg-[var(--kundali-crimson-bg)]/80 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {t.deleteProfileButton}
                </button>
              </>
            ) : null}

            {!activeProfile?.is_synthetic_sample ? (
              <button
                type="button"
                onClick={handleLoadSample}
                className="rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-2.5 py-1 text-xs font-semibold text-[var(--kundali-emerald)] hover:bg-[var(--kundali-emerald-bg)]/80"
              >
                {t.syntheticPreviewButton}
              </button>
            ) : null}
          </div>

          <div className="relative flex min-w-0 flex-wrap items-center gap-2 max-sm:w-full">
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
                  className={`px-2 py-1 font-semibold ${
                    displayCalendar === opt.id
                      ? "bg-[var(--kundali-navy)] text-[var(--kundali-cream)]"
                      : "text-[var(--kundali-ink)] hover:bg-[var(--kundali-strip)]"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <span className="hidden rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2 py-1 font-mono text-[11px] text-[var(--kundali-muted)] md:inline-block">
              {resolvedSettings.ayanamsha} · {resolvedSettings.node_type} ·{" "}
              {resolvedSettings.house_system} · {resolvedSettings.year_days}d
            </span>

            <button
              ref={settingsTriggerRef}
              type="button"
              aria-haspopup="dialog"
              aria-expanded={settingsOpen}
              onClick={() => {
                setStagedSettings(appliedSettings);
                setSettingsOpen((v) => !v);
              }}
              className="rounded bg-[var(--kundali-navy)] px-3 py-1.5 text-xs font-semibold text-[var(--kundali-cream)] hover:bg-[var(--kundali-navy-hover)]"
            >
              {t.settingsButton}
            </button>

            <CalculationSettingsPopover
              open={settingsOpen}
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
        </div>
      </div>

      {/* Main Content */}
      <main id="workspace-main" tabIndex={-1} className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-5 sm:px-6">
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
            className="mb-4 rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-4 py-3 text-xs"
          >
            <p className="font-semibold text-[var(--kundali-crimson)]">{t.logoutConfirmTitle}</p>
            <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">{t.logoutConfirmBody}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={isSigningOutAll}
                onClick={() => void handleConfirmLogoutAll()}
                className="inline-flex min-h-[36px] items-center rounded bg-[var(--kundali-crimson)] px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSigningOutAll ? t.signingOutAllButton : t.logoutConfirmProceed}
              </button>
              <button
                type="button"
                disabled={isSigningOutAll}
                onClick={() => setShowLogoutAllConfirm(false)}
                className="inline-flex min-h-[36px] items-center rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--kundali-ink)]"
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
                {session?.error?.message ?? t.sessionUnavailableBannerBody}
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
          <div className="mb-4 rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-4 py-2.5 text-xs font-medium text-[var(--kundali-muted)]">
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

        {displayCalendar !== "AD" ? (
          <div className="mb-4 rounded border border-[var(--kundali-slate-border)] bg-[var(--kundali-slate-bg)]/45 px-3.5 py-2 text-xs text-[var(--kundali-ink)]">
            {t.bsDisplayPending}
          </div>
        ) : null}

        {showDashaNotice ? (
          <div className="mb-4 rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-3.5 py-2 text-xs font-medium text-[var(--kundali-emerald)]">
            {t.dashaOnlyNotice}
          </div>
        ) : null}

        {isAuthenticated && !isLoadingProfiles && !activeProfile ? (
          <p role="status" className="mb-4 text-sm text-[var(--kundali-muted)]">
            {t.selectProfileForChart}
          </p>
        ) : null}

        {showForm ? (
          <BirthProfileForm
            key={editingTarget ? `edit-${editingTarget.id}` : "create-profile"}
            mode={effectiveFormMode}
            initialProfile={editingTarget}
            canCancel={Boolean(activeProfile)}
            isAuthenticated={isAuthenticated}
            isSubmitting={isSubmittingForm}
            serverErrors={formServerErrors}
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
        ) : (
          <>
            {/* Mobile view switcher (<768px) */}
            <div
              className="mb-4 grid grid-cols-2 gap-2 md:hidden"
              role="group"
              aria-label="Workspace view"
            >
              <button
                type="button"
                aria-pressed={mobilePane === "chart"}
                onClick={() => setMobilePane("chart")}
                className={`rounded border px-3 py-2 text-xs font-semibold ${
                  mobilePane === "chart"
                    ? "border-[var(--kundali-navy)] bg-[var(--kundali-navy)] text-[var(--kundali-cream)]"
                    : "border-[var(--kundali-border)] bg-[var(--kundali-surface)] text-[var(--kundali-ink)]"
                }`}
              >
                {t.mobileViewChart}
              </button>
              <button
                type="button"
                aria-pressed={mobilePane === "secondary"}
                onClick={() => setMobilePane("secondary")}
                className={`rounded border px-3 py-2 text-xs font-semibold ${
                  mobilePane === "secondary"
                    ? "border-[var(--kundali-navy)] bg-[var(--kundali-navy)] text-[var(--kundali-cream)]"
                    : "border-[var(--kundali-border)] bg-[var(--kundali-surface)] text-[var(--kundali-ink)]"
                }`}
              >
                {t.mobileViewSecondary}
              </button>
            </div>

            <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.22fr)_minmax(360px,0.78fr)]">
              {/* Primary Left Pane */}
              <div
                className={`space-y-4 ${
                  mobilePane === "secondary" ? "hidden md:block" : "block"
                }`}
              >
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
                  <div className="flex min-h-16 flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-4 py-3 text-xs">
                    <div className="min-w-0 flex-1 basis-40 leading-relaxed">
                      <p role="status" className="font-semibold text-[var(--kundali-navy)]">
                        {isCalculating ? t.calculatingChart : result ? t.chartCalculated : chartIssue ? "" : t.readyToCalculate}
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
                        className="rounded bg-[var(--kundali-navy)] px-3 py-1.5 font-semibold text-[var(--kundali-cream)] hover:bg-[var(--kundali-navy-hover)] aria-disabled:opacity-60"
                      >
                        {canRetryChart ? t.retryChart : result ? t.recalculateChart : t.calculateChart}
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

                {/* Adaptive Chart + Table Grid: stacks unless primary pane has >= 860px width */}
                <div className="@container grid grid-cols-1 gap-4 @[860px]:grid-cols-[minmax(300px,340px)_minmax(0,1fr)]">
                  <section
                    aria-label={t.chartSectionTitle}
                    className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] p-4"
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
                            className={`px-2.5 py-1 font-semibold ${
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
                    className="min-w-0 rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] p-4"
                  >
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-[var(--kundali-border-subtle)] pb-2.5">
                      <h2 className="text-sm font-semibold text-[var(--kundali-navy)]">
                        {t.tableSectionTitle}
                      </h2>
                      {chart ? (
                        <span className="min-w-0 break-all font-mono text-[11px] text-[var(--kundali-muted)]">
                          {chart.chart_id} · v{chart.engine_version}
                        </span>
                      ) : null}
                    </div>
                    {result ? (
                      <p className="mb-3 break-words font-mono text-[11px] text-[var(--kundali-muted)] md:hidden">
                        {resolvedSettings.ayanamsha} · {resolvedSettings.node_type} ·{" "}
                        {resolvedSettings.house_system} · {resolvedSettings.year_days}d
                      </p>
                    ) : null}

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
                  </section>
                </div>
              </div>

              {/* Secondary Right Pane */}
              <div className={mobilePane === "chart" ? "hidden md:block" : "block"}>
                <SecondaryContractTabs
                  activeTab={activeTab}
                  onChangeTab={setActiveTab}
                  chart={chart}
                  settings={appliedSettings}
                  unknownTimeMode={unknownTimeMode}
                  labels={{
                    tabChat: t.tabChat,
                    tabDasha: t.tabDasha,
                    tabTransits: t.tabTransits,
                    chatContractTitle: t.chatContractTitle,
                    chatContractBody: t.chatContractBody,
                    chatAllowlistTitle: t.chatAllowlistTitle,
                    chatExcludedTitle: t.chatExcludedTitle,
                    chatExcludedList: t.chatExcludedList,
                    chatComposerPlaceholder: t.chatComposerPlaceholder,
                    chatSubmitDisabled: t.chatSubmitDisabled,
                    dashaContractTitle: t.dashaContractTitle,
                    dashaContractBody: t.dashaContractBody,
                    dashaHierarchyLabel: t.dashaHierarchyLabel,
                    dashaConventionLabel: t.dashaConventionLabel,
                    transitsContractTitle: t.transitsContractTitle,
                    transitsContractBody: t.transitsContractBody,
                    stubBadge: t.stubBadge,
                    unavailableNoChart: t.unavailableNoChart,
                    compatibilityUnavailable: t.compatibilityUnavailable,
                  }}
                />
              </div>
            </div>
          </>
        )}
      </main>

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
