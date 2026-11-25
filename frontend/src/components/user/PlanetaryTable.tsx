"use client";

import React from "react";
import { formatDegreeInSign, getLagnaFact, getPlacementFacts } from "@/lib/kundali/chart-helpers";
import { NAKSHATRA_NE, PLANET_LABELS, ZODIAC_SIGNS } from "@/lib/kundali/constants";
import type { ChartFacts, Locale } from "@/lib/kundali/types";

interface PlanetaryTableProps {
  chart: ChartFacts | null;
  locale: Locale;
  unknownTimeMode: boolean;
  highlightedFactId: string | null;
  onSelectFact: (factId: string | null) => void;
  labels: {
    caption: string;
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
    emptyNotice: string;
  };
}

export function PlanetaryTable({
  chart,
  locale,
  unknownTimeMode,
  highlightedFactId,
  onSelectFact,
  labels,
}: PlanetaryTableProps) {
  if (unknownTimeMode || !chart) {
    return (
      <div className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-strip)]/45 p-4 text-sm text-[var(--kundali-muted)]">
        {labels.emptyNotice}
      </div>
    );
  }

  const lagna = getLagnaFact(chart);
  const placements = getPlacementFacts(chart);

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-xs tabular-data">
        <caption className="sr-only">{labels.caption}</caption>
        <thead>
          <tr className="border-b-2 border-[var(--kundali-navy)] text-[11px] uppercase tracking-wider text-[var(--kundali-muted)]">
            <th scope="col" className="px-2 py-2 font-semibold">
              {labels.colBody}
            </th>
            <th scope="col" className="px-2 py-2 font-semibold">
              {labels.colSign}
            </th>
            <th scope="col" className="px-2 py-2 font-semibold">
              {labels.colDegree}
            </th>
            <th scope="col" className="px-2 py-2 font-semibold">
              {labels.colHouse}
            </th>
            <th scope="col" className="px-2 py-2 font-semibold">
              {labels.colNakshatra}
            </th>
            <th scope="col" className="px-2 py-2 font-semibold">
              {labels.colMotion}
            </th>
            <th scope="col" className="px-2 py-2 font-semibold">
              {labels.colFactId}
            </th>
          </tr>
        </thead>
        <tbody>
          {lagna ? (
            <tr
              tabIndex={0}
              aria-selected={highlightedFactId === lagna.id}
              onClick={() =>
                onSelectFact(highlightedFactId === lagna.id ? null : lagna.id)
              }
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectFact(highlightedFactId === lagna.id ? null : lagna.id);
                } else if (e.key === "Escape") {
                  onSelectFact(null);
                }
              }}
              className={`cursor-pointer border-b border-[var(--kundali-border-subtle)] transition-colors ${
                highlightedFactId === lagna.id
                  ? "bg-[var(--kundali-emerald-bg)] text-[var(--kundali-ink)]"
                  : "hover:bg-[var(--kundali-strip)]/55"
              }`}
            >
              <td className="px-2 py-2 font-semibold text-[var(--kundali-navy)]">
                {labels.lagnaName}
              </td>
              <td className="px-2 py-2">
                {locale === "ne"
                  ? ZODIAC_SIGNS[lagna.sign_index]?.ne ?? lagna.sign
                  : `${lagna.sign} (${ZODIAC_SIGNS[lagna.sign_index]?.rashiEn ?? ""})`}
              </td>
              <td className="px-2 py-2 font-mono text-[11px]">
                {formatDegreeInSign(lagna.degree)}
              </td>
              <td className="px-2 py-2 font-mono text-[11px]">1</td>
              <td className="px-2 py-2">
                {locale === "ne"
                  ? NAKSHATRA_NE[lagna.nakshatra] ?? lagna.nakshatra
                  : lagna.nakshatra}{" "}
                · {labels.padaWord} {lagna.pada}
              </td>
              <td className="px-2 py-2 text-[var(--kundali-muted)]">—</td>
              <td className="px-2 py-2 font-mono text-[11px] text-[var(--kundali-emerald)]">
                {lagna.id}
              </td>
            </tr>
          ) : null}

          {placements.map((p) => {
            const pMeta = PLANET_LABELS[p.planet];
            const signMeta = ZODIAC_SIGNS[p.sign_index];
            const nakLabel =
              locale === "ne" ? NAKSHATRA_NE[p.nakshatra] ?? p.nakshatra : p.nakshatra;
            const isSelected = highlightedFactId === p.id;
            return (
              <tr
                key={p.id}
                tabIndex={0}
                aria-selected={isSelected}
                onClick={() => onSelectFact(isSelected ? null : p.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelectFact(isSelected ? null : p.id);
                  } else if (e.key === "Escape") {
                    onSelectFact(null);
                  }
                }}
                className={`cursor-pointer border-b border-[var(--kundali-border-subtle)] transition-colors ${
                  isSelected
                    ? "bg-[var(--kundali-emerald-bg)] text-[var(--kundali-ink)]"
                    : "hover:bg-[var(--kundali-strip)]/55"
                }`}
              >
                <td className="px-2 py-2 font-medium text-[var(--kundali-ink)]">
                  {pMeta ? (locale === "ne" ? pMeta.ne : pMeta.en) : p.planet}
                </td>
                <td className="px-2 py-2">
                  {locale === "ne"
                    ? signMeta?.ne ?? p.sign
                    : `${p.sign} (${signMeta?.rashiEn ?? ""})`}
                </td>
                <td className="px-2 py-2 font-mono text-[11px]">
                  {formatDegreeInSign(p.degree)}
                </td>
                <td className="px-2 py-2 font-mono text-[11px]">{p.house}</td>
                <td className="px-2 py-2">
                  {nakLabel} · {labels.padaWord} {p.pada}
                </td>
                <td className="px-2 py-2">
                  {p.retrograde ? (
                    <span className="inline-block rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--kundali-amber)]">
                      {labels.retrogradeLabel}
                    </span>
                  ) : (
                    <span className="text-[var(--kundali-muted)]">{labels.directLabel}</span>
                  )}
                </td>
                <td className="px-2 py-2 font-mono text-[11px] text-[var(--kundali-emerald)]">
                  {p.id}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
