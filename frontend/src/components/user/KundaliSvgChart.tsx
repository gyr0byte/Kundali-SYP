"use client";

import React from "react";
import { getLagnaFact, getPlacementFacts, getWholeSignHouseMap } from "@/lib/kundali/chart-helpers";
import { PLANET_LABELS, ZODIAC_SIGNS } from "@/lib/kundali/constants";
import type { ChartFactPlacement, ChartFacts, ChartStyle, Locale } from "@/lib/kundali/types";

interface KundaliSvgChartProps {
  chart: ChartFacts | null;
  chartStyle: ChartStyle;
  locale: Locale;
  unknownTimeMode: boolean;
  unavailableReason: string | null;
  highlightedFactId: string | null;
  onSelectFact: (factId: string | null) => void;
  labels: {
    chartTitle: string;
    northLabel: string;
    southLabel: string;
    unknownTimeNoticeTitle: string;
    unknownTimeNoticeBody: string;
    unavailableTitle: string;
    houseWord: string;
    lagnaShort: string;
  };
}

interface HousePoint {
  house: number;
  x: number;
  y: number;
  signX: number;
  signY: number;
}

/** Coordinates for the 12 fixed houses in a North Indian diamond chart (360x360 viewBox). */
const NORTH_HOUSE_POINTS: readonly HousePoint[] = [
  { house: 1, x: 180, y: 92, signX: 180, signY: 56 },
  { house: 2, x: 96, y: 44, signX: 96, signY: 25 },
  { house: 3, x: 46, y: 96, signX: 28, signY: 66 },
  { house: 4, x: 92, y: 180, signX: 54, signY: 180 },
  { house: 5, x: 46, y: 266, signX: 28, signY: 298 },
  { house: 6, x: 96, y: 316, signX: 96, signY: 342 },
  { house: 7, x: 180, y: 268, signX: 180, signY: 308 },
  { house: 8, x: 264, y: 316, signX: 264, signY: 342 },
  { house: 9, x: 314, y: 266, signX: 332, signY: 298 },
  { house: 10, x: 268, y: 180, signX: 306, signY: 180 },
  { house: 11, x: 314, y: 96, signX: 332, signY: 66 },
  { house: 12, x: 264, y: 44, signX: 264, signY: 25 },
];

/** Fixed sign cells (0=Aries..11=Pisces) in a 4x4 South Indian Rashi grid. */
const SOUTH_SIGN_CELLS: ReadonlyArray<{ signIndex: number; col: number; row: number }> = [
  { signIndex: 11, col: 0, row: 0 },
  { signIndex: 0, col: 1, row: 0 },
  { signIndex: 1, col: 2, row: 0 },
  { signIndex: 2, col: 3, row: 0 },
  { signIndex: 3, col: 3, row: 1 },
  { signIndex: 4, col: 3, row: 2 },
  { signIndex: 5, col: 3, row: 3 },
  { signIndex: 6, col: 2, row: 3 },
  { signIndex: 7, col: 1, row: 3 },
  { signIndex: 8, col: 0, row: 3 },
  { signIndex: 9, col: 0, row: 2 },
  { signIndex: 10, col: 0, row: 1 },
];

function formatPlanetChip(p: ChartFactPlacement, locale: Locale): string {
  const meta = PLANET_LABELS[p.planet];
  const base = meta ? (locale === "ne" ? meta.glyphNe : meta.glyphEn) : p.planet.slice(0, 2);
  const retro = p.retrograde ? (locale === "ne" ? "(व)" : "(R)") : "";
  const deg = Math.floor(p.degree);
  return `${base}${retro} ${deg}°`;
}

function handleCellKeyDown(
  event: React.KeyboardEvent<SVGGElement>,
  factId: string | null,
  onSelect: (id: string | null) => void
) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    onSelect(factId);
  } else if (event.key === "Escape") {
    event.preventDefault();
    onSelect(null);
  }
}

export function KundaliChartPlaceholder({
  chartStyle = "north",
  loading = false,
}: {
  chartStyle?: ChartStyle;
  loading?: boolean;
}) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 360 360"
      data-testid={loading ? "chart-skeleton" : undefined}
      className={loading ? "block aspect-square w-full max-w-[360px]" : "block w-full"}
    >
      {!loading ? (
        <circle cx="180" cy="180" r="166" fill="none" stroke="var(--kundali-border)" />
      ) : null}
      <g transform={loading ? undefined : "translate(44 44) scale(.7556)"}>
        <rect x="8" y="8" width="344" height="344" fill="var(--kundali-cream)"
          stroke="var(--kundali-border)" strokeWidth="2" />
        <path
          d={chartStyle === "north"
            ? "M8 8l344 344M352 8 8 352M180 8 352 180 180 352 8 180Z"
            : "M8 94h344M8 266h344M94 8v344M266 8v344M180 8v86m0 172v86M8 180h86m172 0h86"}
          fill="none" stroke="var(--kundali-border)" strokeWidth="1.5"
        />
      </g>
    </svg>
  );
}

export function KundaliSvgChart({
  chart,
  chartStyle,
  locale,
  unknownTimeMode,
  unavailableReason,
  highlightedFactId,
  onSelectFact,
  labels,
}: KundaliSvgChartProps) {
  if (unknownTimeMode) {
    return (
      <div
        className="flex aspect-square w-full max-w-[360px] flex-col justify-center rounded border border-[var(--kundali-slate-border)] bg-[var(--kundali-slate-bg)]/45 p-5 text-sm text-[var(--kundali-ink)]"
        role="region"
        aria-label={labels.unknownTimeNoticeTitle}
      >
        <p className="font-semibold text-[var(--kundali-navy)]">{labels.unknownTimeNoticeTitle}</p>
        <p className="mt-2 leading-relaxed text-[var(--kundali-muted)]">
          {labels.unknownTimeNoticeBody}
        </p>
      </div>
    );
  }

  const lagna = getLagnaFact(chart);
  const placements = getPlacementFacts(chart);

  if (!chart || !lagna) {
    return (
      <div
        className="flex aspect-square w-full max-w-[360px] flex-col justify-center rounded border border-[var(--kundali-border)] bg-[var(--kundali-strip)]/60 p-5 text-sm text-[var(--kundali-muted)]"
        role="region"
        aria-label={labels.unavailableTitle}
      >
        <p className="font-semibold text-[var(--kundali-ink)]">{labels.unavailableTitle}</p>
        {unavailableReason ? <p className="mt-1.5 leading-relaxed">{unavailableReason}</p> : null}
      </div>
    );
  }

  const houseSignMap = getWholeSignHouseMap(lagna.sign_index);

  if (chartStyle === "north") {
    return (
      <svg
        viewBox="0 0 360 360"
        className="h-auto w-full max-w-[360px] select-none"
        role="img"
        aria-label={`${labels.chartTitle} — ${labels.northLabel}`}
      >
        <rect
          x="8"
          y="8"
          width="344"
          height="344"
          fill="#FCFBF8"
          stroke="#13293D"
          strokeWidth="2"
        />
        <line x1="8" y1="8" x2="352" y2="352" stroke="#52606D" strokeWidth="1.25" />
        <line x1="352" y1="8" x2="8" y2="352" stroke="#52606D" strokeWidth="1.25" />
        <polygon
          points="180,8 352,180 180,352 8,180"
          fill="none"
          stroke="#13293D"
          strokeWidth="1.6"
        />

        {NORTH_HOUSE_POINTS.map((pt) => {
          const signIdx = houseSignMap[pt.house - 1];
          const sign = ZODIAC_SIGNS[signIdx];
          const housePlanets = placements.filter((p) => p.house === pt.house);
          const primaryTargetId =
            pt.house === 1 ? "f_lagna" : (housePlanets[0]?.id ?? null);
          const isHighlighted =
            (pt.house === 1 && highlightedFactId === "f_lagna") ||
            housePlanets.some((p) => p.id === highlightedFactId);
          const signNum = signIdx + 1;
          const planetTextList = housePlanets.map((p) => formatPlanetChip(p, locale));
          const ariaText = `${labels.houseWord} ${pt.house}: ${
            locale === "ne" ? sign.ne : `${sign.en} (${sign.rashiEn})`
          }${
            housePlanets.length > 0
              ? ` — ${housePlanets.map((p) => p.planet).join(", ")}`
              : ""
          }`;

          return (
            <g
              key={pt.house}
              tabIndex={0}
              role="button"
              aria-label={ariaText}
              aria-pressed={isHighlighted}
              className="group cursor-pointer"
              onClick={() =>
                onSelectFact(
                  isHighlighted && highlightedFactId === primaryTargetId ? null : primaryTargetId
                )
              }
              onKeyDown={(e) => handleCellKeyDown(e, primaryTargetId, onSelectFact)}
            >
              <circle
                cx={pt.x}
                cy={pt.y}
                r="28"
                fill={isHighlighted ? "#E6F4EE" : "transparent"}
                stroke={isHighlighted ? "#1B6B4A" : "transparent"}
                strokeWidth="1.5"
                className="group-focus-visible:stroke-[var(--kundali-amber)]"
              />
              <text
                x={pt.signX}
                y={pt.signY}
                textAnchor="middle"
                fontSize="10"
                className="max-sm:text-[11px]"
                fontWeight="600"
                fill="#4B5966"
              >
                {signNum} · {locale === "ne" ? sign.shortNe : sign.shortEn}
              </text>
              {pt.house === 1 ? (
                <text
                  x={pt.x}
                  y={pt.y - 10}
                  textAnchor="middle"
                  fontSize="11"
                  className="max-sm:text-[13px]"
                  fontWeight="700"
                  fill="#13293D"
                >
                  {labels.lagnaShort} {Math.floor(lagna.degree)}°
                </text>
              ) : null}
              {planetTextList.slice(0, 4).map((line, idx) => (
                <text
                  key={`${pt.house}-${line}-${idx}`}
                  x={pt.x}
                  y={pt.y + (pt.house === 1 ? 6 : -10) + idx * 14}
                  textAnchor="middle"
                  fontSize="11"
                  className="max-sm:text-[13px]"
                  fontWeight="600"
                  fill={isHighlighted ? "#1B6B4A" : "#18222D"}
                >
                  {line}
                </text>
              ))}
              {planetTextList.length > 4 ? (
                <text
                  x={pt.x}
                  y={pt.y + 44}
                  textAnchor="middle"
                  fontSize="10"
                  fill="#4B5966"
                >
                  +{planetTextList.length - 4}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
    );
  }

  // South Indian 4x4 fixed-sign grid (360x360 viewBox, each cell 86x86 inside 8px padding)
  const cellSize = 86;
  const pad = 8;

  return (
    <svg
      viewBox="0 0 360 360"
      className="h-auto w-full max-w-[360px] select-none"
      role="img"
      aria-label={`${labels.chartTitle} — ${labels.southLabel}`}
    >
      <rect
        x={pad}
        y={pad}
        width={cellSize * 4}
        height={cellSize * 4}
        fill="#FCFBF8"
        stroke="#13293D"
        strokeWidth="2"
      />
      <rect
        x={pad + cellSize}
        y={pad + cellSize}
        width={cellSize * 2}
        height={cellSize * 2}
        fill="#F7F6F1"
        stroke="#13293D"
        strokeWidth="1.25"
      />
      <text
        x="180"
        y="168"
        textAnchor="middle"
        fontSize="13"
        fontWeight="700"
        fill="#13293D"
      >
        {locale === "ne" ? "कुण्डली" : "Kundali"}
      </text>
      <text x="180" y="186" textAnchor="middle" fontSize="10.5" fill="#4B5966">
        {chart.settings.ayanamsha.toUpperCase()} · {chart.settings.node_type.toUpperCase()}
      </text>
      {SOUTH_SIGN_CELLS.map(({ signIndex, col, row }) => {
        const x = pad + col * cellSize;
        const y = pad + row * cellSize;
        const sign = ZODIAC_SIGNS[signIndex];
        const isLagnaSign = lagna.sign_index === signIndex;
        const cellPlanets = placements.filter((p) => p.sign_index === signIndex);
        const primaryTargetId = isLagnaSign ? "f_lagna" : (cellPlanets[0]?.id ?? null);
        const isHighlighted =
          (isLagnaSign && highlightedFactId === "f_lagna") ||
          cellPlanets.some((p) => p.id === highlightedFactId);
        const houseNum = ((signIndex - lagna.sign_index + 12) % 12) + 1;
        const ariaText = `${locale === "ne" ? sign.ne : `${sign.en} (${sign.rashiEn})`} (${
          labels.houseWord
        } ${houseNum})${
          isLagnaSign ? `, ${labels.lagnaShort}` : ""
        }${
          cellPlanets.length > 0 ? `: ${cellPlanets.map((p) => p.planet).join(", ")}` : ""
        }`;

        return (
          <g
            key={signIndex}
            tabIndex={0}
            role="button"
            aria-label={ariaText}
            aria-pressed={isHighlighted}
            className="group cursor-pointer"
            onClick={() =>
              onSelectFact(
                isHighlighted && highlightedFactId === primaryTargetId ? null : primaryTargetId
              )
            }
            onKeyDown={(e) => handleCellKeyDown(e, primaryTargetId, onSelectFact)}
          >
            <rect
              x={x}
              y={y}
              width={cellSize}
              height={cellSize}
              fill={isHighlighted ? "#E6F4EE" : "transparent"}
              stroke={isHighlighted ? "#1B6B4A" : "#52606D"}
              strokeWidth={isHighlighted ? "2" : "1"}
              className="group-focus-visible:stroke-[var(--kundali-amber)] group-focus-visible:stroke-2"
            />
            {isLagnaSign ? (
              <line
                x1={x}
                y1={y + 18}
                x2={x + 18}
                y2={y}
                stroke="#B85D0A"
                strokeWidth="1.75"
              />
            ) : null}
            <text x={x + 6} y={y + 14} fontSize="9.5" className="max-sm:text-[10.5px]" fontWeight="600" fill="#4B5966">
              {locale === "ne" ? sign.shortNe : sign.shortEn} · H{houseNum}
            </text>
            {isLagnaSign ? (
              <text
                x={x + cellSize - 6}
                y={y + 14}
                textAnchor="end"
                fontSize="9.5"
                fontWeight="700"
                fill="#B85D0A"
              >
                {labels.lagnaShort}
              </text>
            ) : null}
            {cellPlanets.slice(0, 4).map((p, idx) => (
              <text
                key={p.id}
                x={x + 7}
                y={y + 30 + idx * 13}
                fontSize="10.5"
                className="max-sm:text-[12.5px]"
                fontWeight="600"
                fill={p.id === highlightedFactId ? "#1B6B4A" : "#18222D"}
              >
                {formatPlanetChip(p, locale)}
              </text>
            ))}
            {cellPlanets.length > 4 ? (
              <text x={x + 7} y={y + 80} fontSize="9.5" fill="#4B5966">
                +{cellPlanets.length - 4}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}
