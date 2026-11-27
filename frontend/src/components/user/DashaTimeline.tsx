"use client";

import { useEffect, useId, useState } from "react";

import { ApiClientError, type ApiClientConfig } from "@/lib/api/client";
import { readDasha, type DashaBoundary, type DashaResponse } from "@/lib/api/dasha";
import { NAKSHATRA_NE, PLANET_LABELS } from "@/lib/kundali/constants";
import type { Locale } from "@/lib/kundali/types";

export interface DashaLabels {
  title: string;
  calculate: string;
  recalculate: string;
  missingSnapshot: string;
  unknown: string;
  loading: string;
  error: string;
  missing: string;
  retry: string;
  approximate: string;
  historical: string;
  yearLength: string;
  days: string;
  years: string;
  birth: string;
  cycle: string;
  initialBalance: string;
  lookupDate: string;
  lookup: string;
  now: string;
  activeAt: string;
  beforeBirth: string;
  outside: string;
  timeline: string;
  md: string;
  ad: string;
  pd: string;
  endExclusive: string;
}

type RequestState =
  | { status: "loading" }
  | { status: "error"; reason: "error" | "missing" | "unknown" }
  | { status: "ready"; result: DashaResponse };

const control = "min-h-11 rounded border border-[var(--kundali-border)] px-3 py-2 text-sm";

function PlanetName({ lord, locale }: { lord: string; locale: Locale }) {
  return PLANET_LABELS[lord]?.[locale] ?? lord;
}

function Instant({ value }: { value: string }) {
  return <time dateTime={value} className="tabular-data inline-flex flex-wrap gap-x-1.5">
    <span>{value.slice(0, 10)}</span><span>{value.slice(11, 26)} UTC</span>
  </time>;
}

function PeriodRange({ period }: { period: DashaBoundary }) {
  return <span className="flex flex-wrap items-baseline gap-x-2 text-xs text-[var(--kundali-muted)]">
    <Instant value={period.start_utc} />
    <span aria-hidden="true">→</span>
    <Instant value={period.end_utc_exclusive} />
  </span>;
}

export function DashaTimeline({
  snapshotId, chartId, config, locale, labels,
}: {
  snapshotId: string;
  chartId: string;
  config: ApiClientConfig;
  locale: Locale;
  labels: DashaLabels;
}) {
  const id = useId();
  const [lookup, setLookup] = useState(() => ({ instant: new Date().toISOString() }));
  const [date, setDate] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [response, setResponse] = useState<{ lookup: typeof lookup; state: RequestState } | null>(null);
  const { getAccessToken, onUnauthorizedRefresh, baseUrl } = config;

  useEffect(() => {
    const controller = new AbortController();
    readDasha({ getAccessToken, onUnauthorizedRefresh, baseUrl }, snapshotId, lookup.instant, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        const state: RequestState = result.snapshot_id === snapshotId && result.chart_id === chartId
          ? { status: "ready", result }
          : { status: "error", reason: "error" };
        setResponse({ lookup, state });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const reason = error instanceof ApiClientError
          ? error.responseCode === "DASHA_UNKNOWN_BIRTH_TIME" ? "unknown"
            : error.status === 404 ? "missing" : "error"
          : "error";
        setResponse({ lookup, state: { status: "error", reason } });
      });
    return () => controller.abort();
  }, [baseUrl, chartId, getAccessToken, lookup, onUnauthorizedRefresh, snapshotId]);

  const state: RequestState = response?.lookup === lookup ? response.state : { status: "loading" };
  const result = state.status === "ready" ? state.result : null;
  const periods = result?.lookup.periods;
  const selected = result?.mahadashas.find((period) => period.period_id === (
    selectedId ?? periods?.mahadasha.period_id
  )) ?? result?.mahadashas[0];
  const yearFormat = new Intl.NumberFormat(locale === "ne" ? "ne-NP" : "en", { maximumFractionDigits: 4 });
  const balance = result?.initial_balance;
  const remainingYears = balance ? balance.remaining_years.numerator / balance.remaining_years.denominator : 0;
  const balanceLabel = remainingYears > 0 && remainingYears < 0.0001
    ? `< ${yearFormat.format(0.0001)}`
    : yearFormat.format(remainingYears);

  return <section aria-labelledby={id} className="min-w-0 rounded border border-[var(--kundali-border)] bg-white p-4 sm:p-6">
    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--kundali-border)] pb-3">
      <h2 id={id} className="text-xl font-semibold text-[var(--kundali-navy)]">{labels.title}</h2>
      {result && <p className="tabular-data text-sm text-[var(--kundali-muted)]">
        {labels.yearLength} · {yearFormat.format(result.year_days)} {labels.days}
      </p>}
    </div>
    <form className="mt-4 flex flex-wrap items-end gap-2" onSubmit={(event) => {
      event.preventDefault();
      if (date) setLookup({ instant: `${date}T00:00:00Z` });
    }}>
      <label className="grid gap-1 text-sm font-medium">
        {labels.lookupDate}
        <input type="date" required min="0001-01-01" max="9999-12-31" value={date}
          className={control} onChange={(event) => setDate(event.target.value)} />
      </label>
      <button className={`${control} bg-[var(--kundali-navy)] font-semibold text-white`} type="submit">{labels.lookup}</button>
      <button className={control} type="button" onClick={() => {
        setDate("");
        setLookup({ instant: new Date().toISOString() });
      }}>{labels.now}</button>
    </form>
    {state.status === "loading" && <p role="status" className="mt-4 text-sm">{labels.loading}</p>}
    {state.status === "error" && <div className="mt-4 flex flex-wrap items-center gap-2">
      <p role="alert" className="text-sm">{labels[state.reason]}</p>
      <button className={control} type="button" onClick={() => setLookup({ ...lookup })}>{labels.retry}</button>
    </div>}
    {result && balance && <>
      {(result.is_conditional || !result.is_current_profile_revision) && <div className="mt-4 space-y-2 rounded border border-[var(--kundali-amber-border)] bg-[var(--kundali-amber-bg)] p-3 text-sm">
        {result.is_conditional && <p>{labels.approximate}</p>}
        {!result.is_current_profile_revision && <p>{labels.historical}</p>}
      </div>}
      <dl className="mt-4 grid gap-3 border-b border-[var(--kundali-border)] pb-4 text-sm sm:grid-cols-2">
        <div><dt className="font-semibold">{labels.birth}</dt><dd><Instant value={result.birth_utc} /></dd></div>
        <div><dt className="font-semibold">{labels.initialBalance}</dt><dd>
          <PlanetName lord={balance.lord} locale={locale} /> · {locale === "ne" ? NAKSHATRA_NE[balance.nakshatra] ?? balance.nakshatra : balance.nakshatra}
          {" · "}<span className="tabular-data">{balanceLabel} {labels.years}</span>
        </dd></div>
        <div className="sm:col-span-2"><dt className="font-semibold">{labels.cycle}</dt><dd>
          <Instant value={result.start_utc} /> {" → "} <Instant value={result.end_utc_exclusive} />
        </dd></div>
      </dl>
      <div className="mt-4" aria-live="polite">
        {result.lookup.as_of && <p className="text-sm font-semibold">{labels.activeAt} · <Instant value={result.lookup.as_of} /></p>}
        {periods ? <dl className="mt-2 grid grid-cols-1 gap-2 bg-[var(--kundali-strip)] p-3 text-sm min-[400px]:grid-cols-3">
          {([
            [labels.md, periods.mahadasha], [labels.ad, periods.antardasha], [labels.pd, periods.pratyantardasha],
          ] as const).map(([level, period]) => <div key={period.level}>
            <dt className="text-[var(--kundali-muted)]">{level}</dt><dd className="font-semibold"><PlanetName lord={period.lord} locale={locale} /></dd>
          </div>)}
        </dl> : <p className="mt-2 text-sm">{result.lookup.status === "before_birth" ? labels.beforeBirth : labels.outside}</p>}
      </div>
      <h3 className="mt-5 text-base font-semibold text-[var(--kundali-navy)]">{labels.timeline}</h3>
      <div className="my-2 overflow-x-auto pb-2">
        <div className="flex min-w-max gap-1" role="group" aria-label={labels.timeline}>
          {result.mahadashas.map((md) => <button key={md.period_id} type="button"
            className={`${control} tabular-data grid min-w-20 text-left aria-pressed:bg-[var(--kundali-navy)] aria-pressed:text-white`}
            aria-pressed={md.period_id === selected?.period_id} aria-controls={`${id}-period`}
            onClick={() => setSelectedId(md.period_id)}>
            <span className="font-semibold"><PlanetName lord={md.lord} locale={locale} /></span>
            <span className="text-xs">{md.start_utc.slice(0, 4)}</span>
          </button>)}
        </div>
      </div>
      {selected && <div key={selected.period_id} id={`${id}-period`} className="min-w-0 border-t border-[var(--kundali-border)] pt-3">
        <p className="text-sm font-semibold">{labels.md} · <PlanetName lord={selected.lord} locale={locale} /></p>
        <PeriodRange period={selected} />
        <p className="my-3 text-xs text-[var(--kundali-muted)]">{labels.endExclusive}</p>
        <h4 className="text-sm font-semibold">{labels.ad}</h4>
        <ul className="mt-2 divide-y divide-[var(--kundali-border)] border-y border-[var(--kundali-border)]">
          {selected.children.map((ad) => <li key={ad.period_id}><details>
            <summary className="min-h-11 cursor-pointer px-2 py-2 text-sm">
              <span className="font-semibold"><PlanetName lord={ad.lord} locale={locale} /></span>
              <PeriodRange period={ad} />
            </summary>
            <div className="bg-[var(--kundali-strip)] px-3 py-2">
              <p className="text-sm font-semibold">{labels.pd}</p>
              <ul className="divide-y divide-[var(--kundali-border)]">
                {ad.children.map((pd) => <li key={pd.period_id} className="py-2 text-sm">
                  <PlanetName lord={pd.lord} locale={locale} /><PeriodRange period={pd} />
                </li>)}
              </ul>
            </div>
          </details></li>)}
        </ul>
      </div>}
    </>}
  </section>;
}
