"use client";

import React, { useState } from "react";
import { COMMON_TIMEZONES } from "@/lib/kundali/constants";
import type { ApiClientConfig } from "@/lib/api/client";
import {
  getInitialProfileFormValues,
  isProfileDateIssue,
  isProfileTimeIssue,
  validateProfileFormInput,
  type ProfileDateIssue,
  type ProfileInputIssue,
  type ProfileTimeIssue,
} from "@/lib/kundali/profile-workflow";
import type {
  BirthProfile,
  BirthProfileCreatePayload,
  BirthplaceSuggestion,
  CalendarType,
  TimeCertainty,
} from "@/lib/kundali/types";
import { BirthplaceSearch, type BirthplaceLabels } from "./BirthplaceSearch";

interface BirthProfileFormProps {
  mode: "create" | "edit";
  initialProfile?: BirthProfile | null;
  canCancel: boolean;
  isAuthenticated: boolean;
  isSubmitting?: boolean;
  serverErrors?: readonly string[] | ProfileInputIssue;
  locale: "en" | "ne";
  searchConfig: ApiClientConfig;
  onInputChange: () => void;
  onSubmitProfile: (payload: BirthProfileCreatePayload) => Promise<void> | void;
  onLoadSyntheticSample: () => void;
  onCancel?: () => void;
  labels: {
    formTitle: string;
    editFormTitle: string;
    formSubtitle: string;
    authFormLockedNotice: string;
    formLabel: string;
    formLabelPlaceholder: string;
    formInputCalendar: string;
    formDate: string;
    formDateHint: string;
    formBsRange: string;
    formDateErrors: Record<ProfileDateIssue, string>;
    formTimeErrors: Record<ProfileTimeIssue, string>;
    formLocation: BirthplaceLabels;
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
    formCancel: string;
    loadSampleButton: string;
    timeExact: string;
    timeApproximate: string;
    timeUnknown: string;
  };
}

export function BirthProfileForm({
  mode,
  initialProfile,
  canCancel,
  isAuthenticated,
  isSubmitting = false,
  serverErrors = [],
  locale,
  searchConfig,
  onInputChange,
  onSubmitProfile,
  onLoadSyntheticSample,
  onCancel,
  labels,
}: BirthProfileFormProps) {
  const initialValues = getInitialProfileFormValues(mode === "edit" ? initialProfile : null);

  const [label, setLabel] = useState(initialValues.label);
  const [inputCalendar, setInputCalendar] = useState<CalendarType>(initialValues.inputCalendar);
  const [enteredDate, setEnteredDate] = useState(initialValues.enteredDate);
  const [certainty, setCertainty] = useState<TimeCertainty>(initialValues.certainty);
  const [timeLocal, setTimeLocal] = useState(initialValues.timeLocal);
  const [placeName, setPlaceName] = useState(initialValues.placeName);
  const [timezone, setTimezone] = useState(initialValues.timezone);
  const [latitude, setLatitude] = useState(initialValues.latitude);
  const [longitude, setLongitude] = useState(initialValues.longitude);
  const [clientError, setClientError] = useState<string | null>(null);
  const [inputIssue, setInputIssue] = useState<ProfileInputIssue | null>(null);
  const [manual, setManual] = useState(mode === "edit");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  function resetIssue() {
    setInputIssue(null);
    setClientError(null);
    onInputChange();
  }

  function clearSelection() {
    if (selectedId === null) return;
    setSelectedId(null);
    setTimezone("");
    setLatitude("");
    setLongitude("");
  }

  function selectBirthplace(place: BirthplaceSuggestion) {
    resetIssue();
    setSelectedId(place.id);
    setPlaceName(place.name);
    setTimezone(place.timezone);
    setLatitude(String(place.latitude));
    setLongitude(String(place.longitude));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!isAuthenticated || isSubmitting) {
      return;
    }

    if (!manual && selectedId === null) {
      setInputIssue("missing_birthplace");
      document.getElementById("bp-place")?.focus();
      return;
    }
    const validation = validateProfileFormInput({
      label,
      inputCalendar,
      enteredDate,
      certainty,
      timeLocal,
      placeName,
      timezone,
      latitude,
      longitude,
    });

    if (validation.error || !validation.payload) {
      const issue = validation.dateIssue ?? validation.locationIssue;
      setInputIssue(issue ?? null);
      setClientError(issue ? null : validation.error);
      return;
    }

    setInputIssue(null);
    setClientError(null);
    await onSubmitProfile({
      ...validation.payload,
      ...(selectedId === null ? {} : {location_id: selectedId}),
    });
  }

  const visibleIssue = inputIssue ?? (typeof serverErrors === "string" ? serverErrors : null);
  const dateIssue = isProfileDateIssue(visibleIssue) ? visibleIssue : null;
  const timeIssue = isProfileTimeIssue(visibleIssue) ? visibleIssue : null;
  const locationIssue = visibleIssue === "missing_birthplace" || visibleIssue === "invalid_birthplace";
  const issueMessage = dateIssue ? labels.formDateErrors[dateIssue] :
    timeIssue ? labels.formTimeErrors[timeIssue] :
    visibleIssue === "missing_birthplace" ? labels.formLocation.select :
    visibleIssue === "invalid_birthplace" ? labels.formLocation.invalid :
    visibleIssue === "invalid_manual_location" ? labels.formLocation.manualInvalid : null;
  const displayedErrors = issueMessage ? [issueMessage] : clientError
    ? [clientError]
    : typeof serverErrors === "string" ? [] : serverErrors;

  const titleText = mode === "edit" ? labels.editFormTitle : labels.formTitle;
  const submitText = isSubmitting
    ? labels.formSaving
    : mode === "edit"
      ? labels.editFormSubmit
      : labels.formSubmit;

  return (
    <section
      aria-labelledby="create-profile-heading"
      className="mx-auto w-full max-w-2xl rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--kundali-border-subtle)] pb-4">
        <div>
          <h2 id="create-profile-heading" className="text-lg font-bold text-[var(--kundali-navy)]">
            {titleText}
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-[var(--kundali-muted)]">
            {labels.formSubtitle}
          </p>
        </div>
        <button
          type="button"
          onClick={onLoadSyntheticSample}
          className="rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-3 py-1.5 text-xs font-semibold text-[var(--kundali-emerald)] hover:bg-[var(--kundali-emerald-bg)]/80"
        >
          {labels.loadSampleButton}
        </button>
      </div>

      {!isAuthenticated ? (
        <div
          role="status"
          className="mt-4 rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] px-3.5 py-2.5 text-xs font-medium text-[var(--kundali-amber)]"
        >
          {labels.authFormLockedNotice}
        </div>
      ) : null}

      <form onSubmit={handleSubmit} className="mt-4 space-y-4 text-xs" noValidate>
        {displayedErrors.length > 0 ? (
          <div
            id="bp-errors"
            role="alert"
            className="rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-3 py-2 font-medium text-[var(--kundali-crimson)]"
          >
            {displayedErrors.length === 1 ? (
              <p>{displayedErrors[0]}</p>
            ) : (
              <ul className="list-disc space-y-1 pl-4">
                {displayedErrors.map((err) => (
                  <li key={err}>{err}</li>
                ))}
              </ul>
            )}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label htmlFor="bp-label" className="block font-semibold text-[var(--kundali-ink)]">
              {labels.formLabel}
            </label>
            <input
              id="bp-label"
              type="text"
              required
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={labels.formLabelPlaceholder}
              className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 text-sm text-[var(--kundali-ink)]"
            />
          </div>

          <div>
            <span className="block font-semibold text-[var(--kundali-ink)]">
              {labels.formInputCalendar}
            </span>
            <div
              className="mt-1 grid grid-cols-2 gap-2"
              role="group"
              aria-label={labels.formInputCalendar}
            >
              {(["BS", "AD"] as const).map((cal) => (
                <button
                  key={cal}
                  type="button"
                  aria-pressed={inputCalendar === cal}
                  onClick={() => {
                    setInputCalendar(cal);
                    resetIssue();
                  }}
                  className={`rounded border px-3 py-2 font-semibold ${
                    inputCalendar === cal
                      ? "border-[var(--kundali-navy)] bg-[var(--kundali-navy)] text-[var(--kundali-cream)]"
                      : "border-[var(--kundali-border)] bg-[var(--kundali-cream)] text-[var(--kundali-ink)]"
                  }`}
                >
                  {cal}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label htmlFor="bp-date" className="block font-semibold text-[var(--kundali-ink)]">
              {labels.formDate} ({inputCalendar})
            </label>
            <input
              id="bp-date"
              type="text"
              required
              aria-invalid={dateIssue !== null}
              aria-describedby={dateIssue ? "bp-date-hint bp-errors" : "bp-date-hint"}
              value={enteredDate}
              onChange={(e) => {
                setEnteredDate(e.target.value);
                resetIssue();
              }}
              placeholder="YYYY-MM-DD"
              className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 font-mono text-sm text-[var(--kundali-ink)]"
            />
            <p id="bp-date-hint" className="mt-1 text-[11px] leading-relaxed text-[var(--kundali-muted)]">
              {labels.formDateHint}{inputCalendar === "BS" ? ` ${labels.formBsRange}` : ""}
            </p>
          </div>

          <div>
            <label
              htmlFor="bp-certainty"
              className="block font-semibold text-[var(--kundali-ink)]"
            >
              {labels.formCertainty}
            </label>
            <select
              id="bp-certainty"
              value={certainty}
              onChange={(e) => {
                const next = e.target.value as TimeCertainty;
                setCertainty(next);
                if (next === "unknown") {
                  setTimeLocal("");
                }
              }}
              className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 text-sm text-[var(--kundali-ink)]"
            >
              <option value="exact">{labels.timeExact}</option>
              <option value="approximate">{labels.timeApproximate}</option>
              <option value="unknown">{labels.timeUnknown}</option>
            </select>
          </div>

          <div>
            <label htmlFor="bp-time" className="block font-semibold text-[var(--kundali-ink)]">
              {labels.formTime}
            </label>
            <input
              id="bp-time"
              type="time"
              aria-invalid={timeIssue !== null}
              aria-describedby={timeIssue ? "bp-errors" : undefined}
              disabled={certainty === "unknown"}
              value={certainty === "unknown" ? "" : timeLocal}
              onChange={(e) => { setTimeLocal(e.target.value); resetIssue(); }}
              className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 font-mono text-sm text-[var(--kundali-ink)] disabled:cursor-not-allowed disabled:bg-[var(--kundali-strip)]"
            />
            {certainty === "unknown" ? (
              <p className="mt-1 text-[11px] text-[var(--kundali-muted)]">
                {labels.formTimeUnknownNote}
              </p>
            ) : null}
          </div>

          <div className="space-y-2 sm:col-span-2">
            {manual ? (
              <div>
                <label htmlFor="bp-place" className="block font-semibold text-[var(--kundali-ink)]">
                  {labels.formPlace}
                </label>
                <input id="bp-place" name="birthplace" type="text" required maxLength={200}
                  value={placeName}
                  onChange={(event) => { setPlaceName(event.target.value); resetIssue(); }}
                  placeholder={labels.formPlacePlaceholder}
                  className="mt-1 w-full rounded border border-[var(--kundali-border)] px-3 py-2 text-sm"
                />
              </div>
            ) : (
              <BirthplaceSearch label={labels.formPlace} value={placeName}
                placeholder={labels.formPlacePlaceholder} labels={labels.formLocation}
                config={searchConfig} locale={locale} enabled={isAuthenticated}
                selectedId={selectedId} invalid={locationIssue}
                onChange={(value) => { setPlaceName(value); clearSelection(); resetIssue(); }}
                onSelect={selectBirthplace}
              />
            )}
            {selectedId !== null && (
              <p role="status" className="break-words text-[var(--kundali-ink)]">
                {labels.formLocation.details} <span className="font-mono">{latitude}, {longitude} · {timezone}</span>
              </p>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button type="button" aria-expanded={manual} aria-controls="bp-location-details"
                onClick={() => { clearSelection(); setManual(!manual); resetIssue(); }}
                className="rounded border border-[var(--kundali-border)] px-3 py-2 font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-strip)]">
                {manual ? labels.formLocation.search : labels.formLocation.manual}
              </button>
              {!manual && (
                <a href="https://www.geonames.org/" className="text-[var(--kundali-muted)] underline">
                  {labels.formLocation.attribution}
                </a>
              )}
            </div>
          </div>

          <div
            id="bp-location-details"
            hidden={!manual}
            role="group"
            aria-label={labels.formLocation.manual}
            aria-describedby={visibleIssue === "invalid_manual_location" ? "bp-errors" : undefined}
            className={manual ? "grid grid-cols-1 gap-4 sm:col-span-2 sm:grid-cols-2" : "hidden"}
          >
            <div>
              <label htmlFor="bp-tz" className="block font-semibold text-[var(--kundali-ink)]">
                {labels.formTimezone}
              </label>
              <input
                id="bp-tz"
                type="text"
                list="bp-iana-tz-list"
                required
                value={timezone}
                onChange={(e) => { setTimezone(e.target.value); resetIssue(); }}
                placeholder={labels.formTimezonePlaceholder}
                className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 font-mono text-xs text-[var(--kundali-ink)]"
              />
              <datalist id="bp-iana-tz-list">
                {COMMON_TIMEZONES.map((tz) => (
                  <option key={tz} value={tz} />
                ))}
              </datalist>
            </div>

            <div>
              <label htmlFor="bp-lat" className="block font-semibold text-[var(--kundali-ink)]">
                {labels.formLatitude}
              </label>
              <input
                id="bp-lat"
                type="number"
                step="any"
                min={-90}
                max={90}
                required
                value={latitude}
                onChange={(e) => { setLatitude(e.target.value); resetIssue(); }}
                placeholder={labels.formLatitudePlaceholder}
                className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 font-mono text-sm text-[var(--kundali-ink)]"
              />
            </div>

            <div>
              <label htmlFor="bp-lon" className="block font-semibold text-[var(--kundali-ink)]">
                {labels.formLongitude}
              </label>
              <input
                id="bp-lon"
                type="number"
                step="any"
                min={-180}
                max={180}
                required
                value={longitude}
                onChange={(e) => { setLongitude(e.target.value); resetIssue(); }}
                placeholder={labels.formLongitudePlaceholder}
                className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 font-mono text-sm text-[var(--kundali-ink)]"
              />
            </div>

            <p className="sm:col-span-2 text-[11px] leading-relaxed text-[var(--kundali-muted)]">
              {labels.formCoordinatesNote}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-[var(--kundali-border-subtle)] pt-4">
          {canCancel && onCancel ? (
            <button
              type="button"
              disabled={isSubmitting}
              onClick={onCancel}
              className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-4 py-2 text-xs font-semibold text-[var(--kundali-ink)] hover:bg-[var(--kundali-strip)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {labels.formCancel}
            </button>
          ) : null}
          <button
            type="submit"
            disabled={!isAuthenticated || isSubmitting}
            className="rounded bg-[var(--kundali-navy)] px-4 py-2 text-xs font-semibold text-[var(--kundali-cream)] hover:bg-[var(--kundali-navy-hover)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitText}
          </button>
        </div>
      </form>
    </section>
  );
}
