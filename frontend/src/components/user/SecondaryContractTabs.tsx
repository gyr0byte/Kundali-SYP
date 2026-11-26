"use client";

import React from "react";
import { buildAllowlistedLlmPayload } from "@/lib/kundali/chart-helpers";
import type { ChartFacts, ChartSettings, WorkspaceTab } from "@/lib/kundali/types";

interface SecondaryContractTabsProps {
  activeTab: WorkspaceTab;
  onChangeTab: (tab: WorkspaceTab) => void;
  chart: ChartFacts | null;
  settings: ChartSettings;
  unknownTimeMode: boolean;
  labels: {
    tabChat: string;
    tabDasha: string;
    tabTransits: string;
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
    stubBadge: string;
    unavailableNoChart: string;
    compatibilityUnavailable: string;
  };
}

const TAB_ORDER: readonly WorkspaceTab[] = ["chat", "dasha", "transits"];

export function SecondaryContractTabs({
  activeTab,
  onChangeTab,
  chart,
  settings,
  unknownTimeMode,
  labels,
}: SecondaryContractTabsProps) {
  const allowlistedPreview =
    chart && !unknownTimeMode
      ? buildAllowlistedLlmPayload(chart, ["f_lagna", "f_moon"])
      : null;

  function handleTabKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, current: WorkspaceTab) {
    const idx = TAB_ORDER.indexOf(current);
    if (event.key === "ArrowRight") {
      event.preventDefault();
      onChangeTab(TAB_ORDER[(idx + 1) % TAB_ORDER.length]);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      onChangeTab(TAB_ORDER[(idx - 1 + TAB_ORDER.length) % TAB_ORDER.length]);
    }
  }

  return (
    <section
      aria-label="Interpretation and timing panels"
      className="flex h-full flex-col rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)]"
    >
      <div
        role="tablist"
        aria-label="Workspace secondary views"
        className="flex flex-wrap border-b border-[var(--kundali-border)] bg-[var(--kundali-strip)]"
      >
        {(
          [
            { id: "chat", label: labels.tabChat },
            { id: "dasha", label: labels.tabDasha },
            { id: "transits", label: labels.tabTransits },
          ] as const
        ).map((tab) => {
          const isSelected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              role="tab"
              type="button"
              aria-selected={isSelected}
              aria-controls={`panel-${tab.id}`}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => onChangeTab(tab.id)}
              onKeyDown={(e) => handleTabKeyDown(e, tab.id)}
              className={`border-r border-[var(--kundali-border)] px-4 py-2.5 text-xs font-semibold transition-colors ${
                isSelected
                  ? "border-t-2 border-t-[var(--kundali-emerald)] bg-[var(--kundali-surface)] text-[var(--kundali-navy)]"
                  : "text-[var(--kundali-muted)] hover:bg-[var(--kundali-cream)] hover:text-[var(--kundali-ink)]"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {activeTab === "chat" ? (
        <div
          id="panel-chat"
          role="tabpanel"
          aria-labelledby="tab-chat"
          className="flex flex-1 flex-col gap-3 p-4 text-xs"
        >
          <div className="flex items-start justify-between gap-2">
            <h2 className="text-sm font-semibold text-[var(--kundali-navy)]">
              {labels.chatContractTitle}
            </h2>
            <span className="shrink-0 rounded border border-[var(--kundali-slate-border)] bg-[var(--kundali-slate-bg)] px-2 py-0.5 font-mono text-[11px] font-medium text-[var(--kundali-ink)]">
              {labels.stubBadge}
            </span>
          </div>

          <p className="leading-relaxed text-[var(--kundali-muted)]">{labels.chatContractBody}</p>

          <div className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-cream)] p-3">
            <p className="font-semibold text-[var(--kundali-ink)]">{labels.chatAllowlistTitle}</p>
            {allowlistedPreview ? (
              <pre className="mt-2 max-h-40 overflow-auto rounded border border-[var(--kundali-border-subtle)] bg-[var(--kundali-surface)] p-2 font-mono text-[11px] leading-snug text-[var(--kundali-ink)]">
                {JSON.stringify(allowlistedPreview, null, 2)}
              </pre>
            ) : (
              <p className="mt-1.5 text-[var(--kundali-muted)]">{labels.unavailableNoChart}</p>
            )}
            <p className="mt-2 font-semibold text-[var(--kundali-ink)]">{labels.chatExcludedTitle}</p>
            <p className="mt-0.5 text-[var(--kundali-muted)]">{labels.chatExcludedList}</p>
          </div>

          <div className="mt-auto flex gap-2 border-t border-[var(--kundali-border-subtle)] pt-3">
            <input
              type="text"
              disabled
              value=""
              placeholder={labels.chatComposerPlaceholder}
              aria-label={labels.chatComposerPlaceholder}
              className="flex-1 cursor-not-allowed rounded border border-[var(--kundali-border)] bg-[var(--kundali-strip)]/60 px-3 py-2 text-xs text-[var(--kundali-muted)]"
            />
            <button
              type="button"
              disabled
              className="cursor-not-allowed rounded bg-[var(--kundali-navy)] px-3.5 py-2 text-xs font-semibold text-[var(--kundali-cream)] opacity-50"
            >
              {labels.chatSubmitDisabled}
            </button>
          </div>
        </div>
      ) : null}

      {activeTab === "dasha" ? (
        <div
          id="panel-dasha"
          role="tabpanel"
          aria-labelledby="tab-dasha"
          className="flex flex-1 flex-col gap-3 p-4 text-xs"
        >
          <div className="flex items-start justify-between gap-2">
            <h2 className="text-sm font-semibold text-[var(--kundali-navy)]">
              {labels.dashaContractTitle}
            </h2>
            <span className="shrink-0 rounded border border-[var(--kundali-slate-border)] bg-[var(--kundali-slate-bg)] px-2 py-0.5 font-mono text-[11px] font-medium text-[var(--kundali-ink)]">
              {labels.stubBadge}
            </span>
          </div>

          <p className="leading-relaxed text-[var(--kundali-muted)]">{labels.dashaContractBody}</p>

          <div className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-cream)] p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-[var(--kundali-ink)]">
                {labels.dashaHierarchyLabel}
              </span>
              <span className="rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-2 py-0.5 font-mono text-[11px] font-medium text-[var(--kundali-emerald)] tabular-data">
                {labels.dashaConventionLabel}: {settings.year_days}d
              </span>
            </div>
            <div className="mt-3 space-y-2 text-[11px] text-[var(--kundali-muted)]">
              <div className="rounded border border-dashed border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2">
                1. Mahadasha (MD) · 120-year proportional timetable track
              </div>
              <div className="rounded border border-dashed border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2">
                2. Antardasha (AD) · 9 sub-periods under selected MD
              </div>
              <div className="rounded border border-dashed border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2">
                3. Pratyantardasha (PD) · 9 sub-periods table under selected AD
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {activeTab === "transits" ? (
        <div
          id="panel-transits"
          role="tabpanel"
          aria-labelledby="tab-transits"
          className="flex flex-1 flex-col gap-3 p-4 text-xs"
        >
          <div className="flex items-start justify-between gap-2">
            <h2 className="text-sm font-semibold text-[var(--kundali-navy)]">
              {labels.transitsContractTitle}
            </h2>
            <span className="shrink-0 rounded border border-[var(--kundali-slate-border)] bg-[var(--kundali-slate-bg)] px-2 py-0.5 font-mono text-[11px] font-medium text-[var(--kundali-ink)]">
              {labels.stubBadge}
            </span>
          </div>

          <p className="leading-relaxed text-[var(--kundali-muted)]">
            {labels.transitsContractBody}
          </p>
        </div>
      ) : null}
      <p className="border-t border-[var(--kundali-border-subtle)] px-4 py-2.5 text-xs text-[var(--kundali-muted)]">
        {labels.compatibilityUnavailable}
      </p>
    </section>
  );
}
