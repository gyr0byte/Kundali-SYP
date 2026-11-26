"use client";

import React, { useEffect, useRef } from "react";
import { classifySettingsChange } from "@/lib/kundali/chart-helpers";
import {
  AYANAMSHA_OPTIONS,
  HAMRO_PATRO_COMPAT_PRESET,
  NODE_TYPE_OPTIONS,
  YEAR_DAYS_OPTIONS,
} from "@/lib/kundali/constants";
import type { ChartSettings, Locale } from "@/lib/kundali/types";

interface CalculationSettingsPopoverProps {
  open: boolean;
  locale: Locale;
  appliedSettings: ChartSettings;
  stagedSettings: ChartSettings;
  onStageChange: (next: ChartSettings) => void;
  onDiscard: () => void;
  onApply: () => void;
  onClose: () => void;
  labels: {
    title: string;
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
  };
}

export function CalculationSettingsPopover({
  open,
  locale,
  appliedSettings,
  stagedSettings,
  onStageChange,
  onDiscard,
  onApply,
  onClose,
  labels,
}: CalculationSettingsPopoverProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) closeButtonRef.current?.focus();
  }, [open]);

  if (!open) return null;

  const scope = classifySettingsChange(appliedSettings, stagedSettings);

  return (
    <div
      role="dialog"
      aria-label={labels.title}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
      className="absolute right-0 top-full z-30 mt-2 w-[min(calc(100vw-2rem),380px)] rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] p-4 shadow-lg"
    >
      <div className="flex items-center justify-between border-b border-[var(--kundali-border-subtle)] pb-2.5">
        <h3 className="text-sm font-semibold text-[var(--kundali-navy)]">{labels.title}</h3>
        <button
          ref={closeButtonRef}
          type="button"
          onClick={onClose}
          className="rounded px-2 py-0.5 text-xs font-medium text-[var(--kundali-muted)] hover:bg-[var(--kundali-strip)]"
        >
          {labels.close}
        </button>
      </div>

      <div className="mt-3 space-y-3 text-xs">
        <div>
          <span className="block font-medium text-[var(--kundali-ink)]">{labels.presetLabel}</span>
          <div className="mt-1.5 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() =>
                onStageChange({
                  ayanamsha: "lahiri",
                  house_system: "whole_sign",
                  node_type: "mean",
                  year_days: 365.25,
                  preset: null,
                })
              }
              className={`rounded border px-2.5 py-1.5 text-left font-medium ${
                stagedSettings.preset === null &&
                stagedSettings.ayanamsha === "lahiri" &&
                stagedSettings.node_type === "mean"
                  ? "border-[var(--kundali-navy)] bg-[var(--kundali-navy)] text-[var(--kundali-cream)]"
                  : "border-[var(--kundali-border)] bg-[var(--kundali-cream)] text-[var(--kundali-ink)] hover:bg-[var(--kundali-strip)]"
              }`}
            >
              {labels.presetStandard}
            </button>
            <button
              type="button"
              onClick={() => onStageChange({ ...HAMRO_PATRO_COMPAT_PRESET })}
              className={`rounded border px-2.5 py-1.5 text-left font-medium ${
                stagedSettings.preset === "hamro_patro_compat"
                  ? "border-[var(--kundali-navy)] bg-[var(--kundali-navy)] text-[var(--kundali-cream)]"
                  : "border-[var(--kundali-border)] bg-[var(--kundali-cream)] text-[var(--kundali-ink)] hover:bg-[var(--kundali-strip)]"
              }`}
            >
              {labels.presetHamro}
            </button>
          </div>
        </div>

        <div>
          <label
            htmlFor="calc-ayanamsha"
            className="block font-medium text-[var(--kundali-ink)]"
          >
            {labels.ayanamshaLabel}
          </label>
          <select
            id="calc-ayanamsha"
            value={stagedSettings.ayanamsha}
            onChange={(e) => {
              const option = AYANAMSHA_OPTIONS.find(({ value }) => value === e.target.value);
              if (option) onStageChange({ ...stagedSettings, ayanamsha: option.value, preset: null });
            }}
            className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2.5 py-1.5 text-xs text-[var(--kundali-ink)]"
          >
            {AYANAMSHA_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {locale === "ne" ? opt.labelNe : opt.labelEn}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label
            htmlFor="calc-node-type"
            className="block font-medium text-[var(--kundali-ink)]"
          >
            {labels.nodeTypeLabel}
          </label>
          <select
            id="calc-node-type"
            value={stagedSettings.node_type}
            onChange={(e) => {
              const option = NODE_TYPE_OPTIONS.find(({ value }) => value === e.target.value);
              if (option) onStageChange({ ...stagedSettings, node_type: option.value, preset: null });
            }}
            className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2.5 py-1.5 text-xs text-[var(--kundali-ink)]"
          >
            {NODE_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {locale === "ne" ? opt.labelNe : opt.labelEn}
              </option>
            ))}
          </select>
        </div>

        <div>
          <span className="block font-medium text-[var(--kundali-ink)]">
            {labels.houseSystemLabel}
          </span>
          <div className="mt-1 rounded border border-[var(--kundali-border-subtle)] bg-[var(--kundali-strip)]/70 px-2.5 py-1.5 text-xs text-[var(--kundali-muted)]">
            {labels.houseSystemFixedValue}
          </div>
        </div>

        <div>
          <label
            htmlFor="calc-year-days"
            className="block font-medium text-[var(--kundali-ink)]"
          >
            {labels.yearDaysLabel}
          </label>
          <select
            id="calc-year-days"
            value={String(stagedSettings.year_days)}
            onChange={(e) => {
              const option = YEAR_DAYS_OPTIONS.find(({ value }) => String(value) === e.target.value);
              if (option) onStageChange({ ...stagedSettings, year_days: option.value });
            }}
            className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-2.5 py-1.5 text-xs text-[var(--kundali-ink)]"
          >
            {YEAR_DAYS_OPTIONS.map((opt) => (
              <option key={opt.value} value={String(opt.value)}>
                {locale === "ne" ? opt.labelNe : opt.labelEn}
              </option>
            ))}
          </select>
        </div>

        <div
          className={`rounded border px-2.5 py-2 text-[11px] leading-relaxed ${
            scope === "none"
              ? "border-[var(--kundali-border-subtle)] bg-[var(--kundali-cream)] text-[var(--kundali-muted)]"
              : scope === "dasha_only"
                ? "border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] text-[var(--kundali-emerald)]"
                : "border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] text-[var(--kundali-ink)]"
          }`}
        >
          {scope === "none"
            ? labels.scopeNone
            : scope === "dasha_only"
              ? labels.scopeDashaOnly
              : labels.scopeFullChart}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-end gap-2 border-t border-[var(--kundali-border-subtle)] pt-3">
        <button
          type="button"
          onClick={onDiscard}
          disabled={scope === "none"}
          className="rounded border border-[var(--kundali-border)] px-3 py-1.5 text-xs font-medium text-[var(--kundali-ink)] hover:bg-[var(--kundali-strip)] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {labels.discard}
        </button>
        <button
          type="button"
          onClick={onApply}
          disabled={scope === "none"}
          className="rounded bg-[var(--kundali-navy)] px-3 py-1.5 text-xs font-semibold text-[var(--kundali-cream)] hover:bg-[var(--kundali-navy-hover)] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {labels.applySettings}
        </button>
      </div>
    </div>
  );
}
