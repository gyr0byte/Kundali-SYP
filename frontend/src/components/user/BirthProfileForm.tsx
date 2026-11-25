"use client";

import React, { useState } from "react";
import { COMMON_TIMEZONES } from "@/lib/kundali/constants";
import type { BirthProfile, CalendarType, TimeCertainty } from "@/lib/kundali/types";

interface BirthProfileFormProps {
  canCancel: boolean;
  onSaveProfile: (profile: BirthProfile) => void;
  onLoadSyntheticSample: () => void;
  onCancel?: () => void;
  labels: {
    formTitle: string;
    formSubtitle: string;
    formLabel: string;
    formLabelPlaceholder: string;
    formInputCalendar: string;
    formDate: string;
    formCertainty: string;
    formTime: string;
    formTimeUnknownNote: string;
    formPlace: string;
    formTimezone: string;
    formLatitude: string;
    formLongitude: string;
    formSubmit: string;
    formCancel: string;
    loadSampleButton: string;
    timeExact: string;
    timeApproximate: string;
    timeUnknown: string;
  };
}

export function BirthProfileForm({
  canCancel,
  onSaveProfile,
  onLoadSyntheticSample,
  onCancel,
  labels,
}: BirthProfileFormProps) {
  const [label, setLabel] = useState("");
  const [inputCalendar, setInputCalendar] = useState<CalendarType>("BS");
  const [enteredDate, setEnteredDate] = useState("2055-04-15");
  const [certainty, setCertainty] = useState<TimeCertainty>("exact");
  const [timeLocal, setTimeLocal] = useState("08:30");
  const [placeName, setPlaceName] = useState("Kathmandu, Nepal");
  const [timezone, setTimezone] = useState("Asia/Kathmandu");
  const [latitude, setLatitude] = useState("27.7172");
  const [longitude, setLongitude] = useState("85.3240");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmedLabel = label.trim();
    if (!trimmedLabel) {
      setErrorMsg("Enter a profile label.");
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(enteredDate.trim())) {
      setErrorMsg("Enter birth date in YYYY-MM-DD format.");
      return;
    }
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
      setErrorMsg("Latitude must be between -90 and 90.");
      return;
    }
    if (!Number.isFinite(lon) || lon < -180 || lon > 180) {
      setErrorMsg("Longitude must be between -180 and 180.");
      return;
    }
    if (certainty !== "unknown" && !/^\d{2}:\d{2}(:\d{2})?$/.test(timeLocal.trim())) {
      setErrorMsg("Enter local birth time (HH:MM) or mark time certainty as Unknown.");
      return;
    }

    setErrorMsg(null);
    const profile: BirthProfile = {
      id: `profile_${Date.now()}`,
      label: trimmedLabel,
      input_calendar: inputCalendar,
      entered_date: enteredDate.trim(),
      date_ad: inputCalendar === "AD" ? enteredDate.trim() : null,
      time_local: certainty === "unknown" ? null : timeLocal.trim(),
      place_name: placeName.trim() || "Unspecified place",
      latitude: lat,
      longitude: lon,
      timezone,
      time_certainty: certainty,
      is_synthetic_sample: false,
    };
    onSaveProfile(profile);
  }

  return (
    <section
      aria-labelledby="create-profile-heading"
      className="mx-auto w-full max-w-2xl rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--kundali-border-subtle)] pb-4">
        <div>
          <h2 id="create-profile-heading" className="text-lg font-bold text-[var(--kundali-navy)]">
            {labels.formTitle}
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

      <form onSubmit={handleSubmit} className="mt-4 space-y-4 text-xs" noValidate>
        {errorMsg ? (
          <div
            role="alert"
            className="rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-3 py-2 font-medium text-[var(--kundali-crimson)]"
          >
            {errorMsg}
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
            <div className="mt-1 grid grid-cols-2 gap-2" role="group" aria-label={labels.formInputCalendar}>
              {(["BS", "AD"] as const).map((cal) => (
                <button
                  key={cal}
                  type="button"
                  aria-pressed={inputCalendar === cal}
                  onClick={() => {
                    setInputCalendar(cal);
                    setEnteredDate(cal === "BS" ? "2055-04-15" : "1998-07-31");
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
              inputMode="numeric"
              value={enteredDate}
              onChange={(e) => setEnteredDate(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 font-mono text-sm text-[var(--kundali-ink)]"
            />
          </div>

          <div>
            <label htmlFor="bp-certainty" className="block font-semibold text-[var(--kundali-ink)]">
              {labels.formCertainty}
            </label>
            <select
              id="bp-certainty"
              value={certainty}
              onChange={(e) => setCertainty(e.target.value as TimeCertainty)}
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
              disabled={certainty === "unknown"}
              value={certainty === "unknown" ? "" : timeLocal}
              onChange={(e) => setTimeLocal(e.target.value)}
              className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 font-mono text-sm text-[var(--kundali-ink)] disabled:cursor-not-allowed disabled:bg-[var(--kundali-strip)]"
            />
            {certainty === "unknown" ? (
              <p className="mt-1 text-[11px] text-[var(--kundali-muted)]">
                {labels.formTimeUnknownNote}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="bp-place" className="block font-semibold text-[var(--kundali-ink)]">
              {labels.formPlace}
            </label>
            <input
              id="bp-place"
              type="text"
              value={placeName}
              onChange={(e) => setPlaceName(e.target.value)}
              className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 text-sm text-[var(--kundali-ink)]"
            />
          </div>

          <div>
            <label htmlFor="bp-tz" className="block font-semibold text-[var(--kundali-ink)]">
              {labels.formTimezone}
            </label>
            <select
              id="bp-tz"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 font-mono text-xs text-[var(--kundali-ink)]"
            >
              {COMMON_TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="bp-lat" className="block font-semibold text-[var(--kundali-ink)]">
              {labels.formLatitude}
            </label>
            <input
              id="bp-lat"
              type="number"
              step="0.0001"
              value={latitude}
              onChange={(e) => setLatitude(e.target.value)}
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
              step="0.0001"
              value={longitude}
              onChange={(e) => setLongitude(e.target.value)}
              className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 font-mono text-sm text-[var(--kundali-ink)]"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-[var(--kundali-border-subtle)] pt-4">
          {canCancel && onCancel ? (
            <button
              type="button"
              onClick={onCancel}
              className="rounded border border-[var(--kundali-border)] px-4 py-2 font-medium text-[var(--kundali-ink)] hover:bg-[var(--kundali-strip)]"
            >
              {labels.formCancel}
            </button>
          ) : null}
          <button
            type="submit"
            className="rounded bg-[var(--kundali-navy)] px-4 py-2 font-semibold text-[var(--kundali-cream)] hover:bg-[var(--kundali-navy-hover)]"
          >
            {labels.formSubmit}
          </button>
        </div>
      </form>
    </section>
  );
}
