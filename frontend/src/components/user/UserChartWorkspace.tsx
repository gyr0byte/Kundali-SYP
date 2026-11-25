"use client";

import React, { useCallback, useEffect, useState } from "react";
import { ApiClientError } from "@/lib/api/client";
import {
  createProfile,
  deleteProfile,
  listProfiles,
  updateProfile,
} from "@/lib/api/profiles";
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
  applyUpdatedProfile,
  createInitialWorkspaceState,
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
  applyAndRecompute: string;
  close: string;
  authRequiredBannerTitle: string;
  authRequiredBannerBody: string;
  authFormLockedNotice: string;
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
  savedProfileChartPendingTitle: string;
  savedProfileBsStatusBadge: string;
  sampleBannerTitle: string;
  sampleBannerBody: string;
  approxBannerTitle: string;
  approxBannerBody: string;
  unknownTimeBannerTitle: string;
  unknownTimeBannerBody: string;
  lagnaSensitivityTitle: string;
  awaitingBsBody: string;
  awaitingApiBody: string;
  awaitingRecomputeBody: string;
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
  /** Optional injected access token provider; omitted until frontend auth milestone lands. */
  getAccessToken?: AccessTokenProvider;
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

function computeProfileState(
  profile: BirthProfile | null,
  settings: ChartSettings
): { state: ChartCalculationState; chart: ChartFacts | null } {
  if (!profile) {
    return { state: "unavailable", chart: null };
  }
  if (profile.input_calendar === "BS" && !profile.date_ad) {
    return { state: "awaiting_bs_conversion", chart: null };
  }
  if (profile.time_certainty === "unknown") {
    return { state: "unknown_time_unimplemented", chart: null };
  }
  if (profile.is_synthetic_sample && profile.id === SAMPLE_NORTH_LONDON_PROFILE.id) {
    const base = SAMPLE_NORTH_LONDON_CHART_FACTS.settings;
    const ephemerisMatches =
      settings.ayanamsha === base.ayanamsha &&
      settings.node_type === base.node_type &&
      settings.preset === base.preset;
    if (!ephemerisMatches) {
      return { state: "awaiting_recompute", chart: null };
    }
    return {
      state: "ready",
      chart: {
        ...SAMPLE_NORTH_LONDON_CHART_FACTS,
        settings: {
          ...SAMPLE_NORTH_LONDON_CHART_FACTS.settings,
          year_days: settings.year_days,
        },
      },
    };
  }
  return { state: "unavailable", chart: null };
}

export function UserChartWorkspace({
  messagesByLocale,
  getAccessToken,
  apiBaseUrl,
}: UserChartWorkspaceProps) {
  const [locale, setLocale] = useState<Locale>("en");
  const [profileState, setProfileState] = useState<ProfileWorkspaceState>(
    createInitialWorkspaceState
  );
  const [authStatus, setAuthStatus] = useState<"checking" | "authenticated" | "unauthenticated">(
    () => (getAccessToken ? "checking" : "unauthenticated")
  );
  const [isLoadingProfiles, setIsLoadingProfiles] = useState<boolean>(false);
  const [formMode, setFormMode] = useState<"closed" | "create" | "edit">("closed");
  const [isSubmittingForm, setIsSubmittingForm] = useState<boolean>(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [isDeletingProfile, setIsDeletingProfile] = useState<boolean>(false);
  const [apiErrorBanner, setApiErrorBanner] = useState<string | null>(null);
  const [formServerErrors, setFormServerErrors] = useState<readonly string[]>([]);
  const [profileActionNotice, setProfileActionNotice] = useState<string | null>(null);

  const [displayCalendar, setDisplayCalendar] = useState<DisplayCalendarPreference>("AD");
  const [appliedSettings, setAppliedSettings] = useState<ChartSettings>(DEFAULT_SETTINGS);
  const [stagedSettings, setStagedSettings] = useState<ChartSettings>(DEFAULT_SETTINGS);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [settingsNotice, setSettingsNotice] = useState<string | null>(null);
  const [chartStyle, setChartStyle] = useState<ChartStyle>("north");
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("chat");
  const [mobilePane, setMobilePane] = useState<"chart" | "secondary">("chart");
  const [highlightedFactId, setHighlightedFactId] = useState<string | null>(null);

  const t = messagesByLocale[locale];
  const isAuthenticated = authStatus === "authenticated";
  const visibleProfiles = resolveVisibleProfiles(profileState);
  const activeProfile = resolveActiveProfile(profileState);
  const { state: calcState, chart } = computeProfileState(activeProfile, appliedSettings);
  const provenanceStatus = getProvenanceStatus(chart, calcState);
  const unknownTimeMode = isUnknownTimeProfile(activeProfile);
  const sensitivityFact = getSensitivityFact(chart);

  const loadSavedProfilesFromApi = useCallback(async () => {
    const token = getAccessToken ? await getAccessToken() : null;
    const validToken = typeof token === "string" ? token.trim() : "";
    if (!validToken) {
      setAuthStatus("unauthenticated");
      setIsLoadingProfiles(false);
      setApiErrorBanner(null);
      return;
    }

    setAuthStatus("authenticated");
    setIsLoadingProfiles(true);
    setApiErrorBanner(null);
    try {
      const response = await listProfiles({ getAccessToken, baseUrl: apiBaseUrl });
      setProfileState((prev) => applyLoadedProfiles(prev, response.items));
    } catch (err) {
      if (
        err instanceof ApiClientError &&
        (err.code === "AUTH_REQUIRED" || err.code === "UNAUTHORIZED")
      ) {
        setAuthStatus("unauthenticated");
        setApiErrorBanner(err.message);
      } else {
        setApiErrorBanner(
          err instanceof Error ? err.message : "Unable to load saved birth profiles."
        );
      }
    } finally {
      setIsLoadingProfiles(false);
    }
  }, [apiBaseUrl, getAccessToken]);

  useEffect(() => {
    let active = true;
    async function hydrate() {
      const token = getAccessToken ? await getAccessToken() : null;
      if (!active) return;
      const validToken = typeof token === "string" ? token.trim() : "";
      if (!validToken) {
        setAuthStatus("unauthenticated");
        setIsLoadingProfiles(false);
        return;
      }
      setAuthStatus("authenticated");
      setIsLoadingProfiles(true);
      try {
        const response = await listProfiles({ getAccessToken, baseUrl: apiBaseUrl });
        if (!active) return;
        setProfileState((prev) => applyLoadedProfiles(prev, response.items));
        setApiErrorBanner(null);
      } catch (err) {
        if (!active) return;
        if (
          err instanceof ApiClientError &&
          (err.code === "AUTH_REQUIRED" || err.code === "UNAUTHORIZED")
        ) {
          setAuthStatus("unauthenticated");
          setApiErrorBanner(err.message);
        } else {
          setApiErrorBanner(
            err instanceof Error ? err.message : "Unable to load saved birth profiles."
          );
        }
      } finally {
        if (active) setIsLoadingProfiles(false);
      }
    }
    void hydrate();
    return () => {
      active = false;
    };
  }, [apiBaseUrl, getAccessToken]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setSettingsOpen(false);
        setHighlightedFactId(null);
        setConfirmDeleteId(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function handleLoadSample() {
    setProfileState((prev) => activateSyntheticSamplePreview(prev));
    setAppliedSettings(DEFAULT_SETTINGS);
    setStagedSettings(DEFAULT_SETTINGS);
    setSettingsNotice(null);
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

  async function handleSubmitProfileForm(payload: BirthProfileCreatePayload) {
    if (!isAuthenticated) return;
    setIsSubmittingForm(true);
    setFormServerErrors([]);
    setApiErrorBanner(null);
    setProfileActionNotice(null);

    try {
      if (formMode === "edit" && activeProfile && !activeProfile.is_synthetic_sample) {
        const updated = await updateProfile(
          { getAccessToken, baseUrl: apiBaseUrl },
          activeProfile.id,
          payload
        );
        setProfileState((prev) => applyUpdatedProfile(prev, updated));
        setProfileActionNotice(t.profileUpdatedNotice);
      } else {
        const created = await createProfile({ getAccessToken, baseUrl: apiBaseUrl }, payload);
        setProfileState((prev) => applyCreatedProfile(prev, created));
        setProfileActionNotice(t.profileCreatedNotice);
      }
      setFormMode("closed");
      setSettingsNotice(null);
      setHighlightedFactId(null);
    } catch (err) {
      if (err instanceof ApiClientError) {
        if (err.code === "AUTH_REQUIRED" || err.code === "UNAUTHORIZED") {
          setAuthStatus("unauthenticated");
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
    setIsDeletingProfile(true);
    setApiErrorBanner(null);
    setProfileActionNotice(null);

    try {
      await deleteProfile({ getAccessToken, baseUrl: apiBaseUrl }, profileId);
      setProfileState((prev) => applyDeletedProfile(prev, profileId));
      setConfirmDeleteId(null);
      setProfileActionNotice(t.profileDeletedNotice);
      setHighlightedFactId(null);
    } catch (err) {
      if (err instanceof ApiClientError && err.code === "UNAUTHORIZED") {
        setAuthStatus("unauthenticated");
      }
      setApiErrorBanner(
        err instanceof Error ? err.message : "Unable to delete saved birth profile."
      );
      setConfirmDeleteId(null);
    } finally {
      setIsDeletingProfile(false);
    }
  }

  function handleApplySettings() {
    const scope = classifySettingsChange(appliedSettings, stagedSettings);
    if (scope === "none") return;
    setAppliedSettings(stagedSettings);
    setSettingsOpen(false);
    setSettingsNotice(scope === "dasha_only" ? t.dashaOnlyNotice : null);
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
        : t.provenanceUnknown;

  const provenanceClasses =
    provenanceStatus === "swieph"
      ? "border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] text-[var(--kundali-emerald)]"
      : provenanceStatus === "moshier"
        ? "border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] text-[var(--kundali-amber)]"
        : "border-[var(--kundali-slate-border)] bg-[var(--kundali-slate-bg)] text-[var(--kundali-ink)]";

  const unavailableReason =
    calcState === "awaiting_bs_conversion"
      ? t.awaitingBsBody
      : calcState === "awaiting_recompute"
        ? t.awaitingRecomputeBody
        : t.awaitingApiBody;

  const showForm = formMode !== "closed" || !activeProfile;
  const effectiveFormMode: "create" | "edit" =
    formMode === "edit" && activeProfile && !activeProfile.is_synthetic_sample ? "edit" : "create";
  const editingTarget = effectiveFormMode === "edit" ? activeProfile : null;
  const showSavedPendingBanner = Boolean(
    activeProfile && !activeProfile.is_synthetic_sample && calcState === "unavailable"
  );

  return (
    <div className="flex min-h-screen flex-col bg-[var(--kundali-cream)] text-[var(--kundali-ink)]">
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
                <circle cx="5" cy="5" r="4" fill="currentColor" />
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
          </div>
        </div>
      </header>

      {/* Profile & Conventions Strip */}
      <div className="border-b border-[var(--kundali-border)] bg-[var(--kundali-strip)] px-4 py-2.5 sm:px-6">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-2.5">
            {visibleProfiles.length > 0 ? (
              <div className="flex flex-wrap items-center gap-2">
                <label htmlFor="active-profile-select" className="sr-only">
                  {t.profileLabel}
                </label>
                <select
                  id="active-profile-select"
                  value={profileState.activeProfileId ?? ""}
                  onChange={(e) => {
                    const nextId = e.target.value;
                    setProfileState((prev) => ({ ...prev, activeProfileId: nextId }));
                    setFormMode("closed");
                    setConfirmDeleteId(null);
                    setFormServerErrors([]);
                    setHighlightedFactId(null);
                  }}
                  className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2.5 py-1.5 text-xs font-semibold text-[var(--kundali-navy)]"
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
                            ? "border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] text-[var(--kundali-amber)]"
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

          <div className="relative flex flex-wrap items-center gap-2">
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
              {appliedSettings.ayanamsha} · {appliedSettings.node_type} ·{" "}
              {appliedSettings.house_system} · {appliedSettings.year_days}d
            </span>

            <button
              type="button"
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
              onClose={() => setSettingsOpen(false)}
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
                applyAndRecompute: t.applyAndRecompute,
                close: t.close,
              }}
            />
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-5 sm:px-6">
        {authStatus === "unauthenticated" ? (
          <div
            role="status"
            className="mb-4 rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] px-4 py-3 text-xs"
          >
            <p className="font-semibold text-[var(--kundali-amber)]">
              {t.authRequiredBannerTitle}
            </p>
            <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">
              {t.authRequiredBannerBody}
            </p>
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
            {profileActionNotice}
          </div>
        ) : null}

        {confirmDeleteId && activeProfile && confirmDeleteId === activeProfile.id ? (
          <div
            role="alertdialog"
            aria-label={t.deleteProfileButton}
            className="mb-4 rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-4 py-3 text-xs"
          >
            <p className="font-semibold text-[var(--kundali-crimson)]">
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

        {settingsNotice ? (
          <div className="mb-4 rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-3.5 py-2 text-xs font-medium text-[var(--kundali-emerald)]">
            {settingsNotice}
          </div>
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
                            setSettingsNotice(null);
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

                {showSavedPendingBanner ? (
                  <div className="rounded border border-[var(--kundali-slate-border)] bg-[var(--kundali-surface)] px-4 py-3 text-xs">
                    <p className="font-semibold text-[var(--kundali-navy)]">
                      {t.savedProfileChartPendingTitle}
                    </p>
                    <p className="mt-1 leading-relaxed text-[var(--kundali-muted)]">
                      {t.awaitingApiBody}
                    </p>
                  </div>
                ) : null}

                {activeProfile?.time_certainty === "approximate" ? (
                  <div className="rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] px-4 py-3 text-xs">
                    <p className="font-semibold text-[var(--kundali-amber)]">
                      {t.approxBannerTitle}
                    </p>
                    <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">
                      {t.approxBannerBody}
                    </p>
                  </div>
                ) : null}

                {sensitivityFact ? (
                  <div className="rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] px-4 py-3 text-xs">
                    <p className="font-semibold text-[var(--kundali-amber)]">
                      {t.lagnaSensitivityTitle}
                    </p>
                    <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">
                      {sensitivityFact.note} ({sensitivityFact.degree_in_sign.toFixed(2)}°;{" "}
                      {sensitivityFact.boundary_distance_degrees.toFixed(2)}° from cusp)
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

                    <div className="flex justify-center">
                      <KundaliSvgChart
                        chart={chart}
                        chartStyle={chartStyle}
                        locale={locale}
                        unknownTimeMode={unknownTimeMode}
                        unavailableReason={unavailableReason}
                        highlightedFactId={highlightedFactId}
                        onSelectFact={setHighlightedFactId}
                        labels={{
                          chartTitle: t.chartSectionTitle,
                          northLabel: t.northLabel,
                          southLabel: t.southLabel,
                          unknownTimeNoticeTitle: t.unknownTimeBannerTitle,
                          unknownTimeNoticeBody: t.unknownTimeBannerBody,
                          unavailableTitle: activeProfile?.label ?? "",
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
                        <span className="font-mono text-[11px] text-[var(--kundali-muted)]">
                          {chart.chart_id} · v{chart.engine_version}
                        </span>
                      ) : null}
                    </div>

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
