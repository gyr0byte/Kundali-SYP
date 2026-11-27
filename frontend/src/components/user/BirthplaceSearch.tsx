"use client";

import { useEffect, useId, useState } from "react";
import { searchBirthplaces } from "@/lib/api/profiles";
import type { ApiClientConfig } from "@/lib/api/client";
import type { BirthplaceSuggestion } from "@/lib/kundali/types";

export interface BirthplaceLabels {
  hint: string;
  loading: string;
  empty: string;
  failed: string;
  attribution: string;
  manual: string;
  search: string;
  select: string;
  invalid: string;
  manualInvalid: string;
  details: string;
}

interface Props {
  label: string;
  value: string;
  placeholder: string;
  labels: BirthplaceLabels;
  config: ApiClientConfig;
  locale: "en" | "ne";
  enabled: boolean;
  selectedId: number | null;
  invalid: boolean;
  onChange: (value: string) => void;
  onSelect: (place: BirthplaceSuggestion) => void;
}

export function BirthplaceSearch({
  label, value, placeholder, labels, config, locale, enabled, selectedId, invalid, onChange, onSelect,
}: Props) {
  const listId = useId();
  const hintId = useId();
  const [expanded, setExpanded] = useState(false);
  const [active, setActive] = useState(-1);
  const [result, setResult] = useState<{ query: string; places: BirthplaceSuggestion[]; failed: boolean }>();
  const query = value.trim();
  const { getAccessToken, onUnauthorizedRefresh, baseUrl } = config;
  const searchable = enabled && selectedId === null && query.length >= 2 && /\p{L}/u.test(query);
  const current = searchable && result?.query === query ? result : undefined;
  const places = current?.places;
  const showOptions = Boolean(expanded && places?.length);

  useEffect(() => {
    if (!searchable || !expanded) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void searchBirthplaces({ getAccessToken, onUnauthorizedRefresh, baseUrl }, query, controller.signal).then(
        (options) => {
          if (!controller.signal.aborted) setResult({ query, places: options, failed: false });
        },
        () => {
          if (!controller.signal.aborted) setResult({ query, places: [], failed: true });
        },
      );
    }, 180);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [baseUrl, expanded, getAccessToken, onUnauthorizedRefresh, query, searchable]);

  function select(place: BirthplaceSuggestion) {
    setExpanded(false);
    setActive(-1);
    onSelect(place);
  }

  return (
    <div className="relative min-w-0">
      <label htmlFor="bp-place" className="block font-semibold text-[var(--kundali-ink)]">{label}</label>
      <input
        id="bp-place"
        name="birthplace"
        type="text"
        autoComplete="off"
        maxLength={80}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showOptions}
        aria-controls={showOptions ? listId : undefined}
        aria-activedescendant={showOptions && places?.[active] ? `${listId}-${active}` : undefined}
        aria-describedby={invalid ? `${hintId} bp-errors` : hintId}
        aria-invalid={invalid}
        value={value}
        placeholder={placeholder}
        onFocus={() => setExpanded(true)}
        onBlur={() => { setExpanded(false); setActive(-1); }}
        onChange={(event) => {
          setExpanded(true);
          setActive(-1);
          setResult(undefined);
          onChange(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing) return;
          if (event.key === "Escape") {
            setExpanded(false);
            setActive(-1);
            return;
          }
          if (places?.length && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
            event.preventDefault();
            setExpanded(true);
            const next = event.key === "ArrowDown" ? (active + 1) % places.length :
              (active > 0 ? active - 1 : places.length - 1);
            setActive(next);
            requestAnimationFrame(() => document.getElementById(`${listId}-${next}`)?.scrollIntoView({ block: "nearest" }));
          } else if (event.key === "Enter" && showOptions) {
            event.preventDefault();
            if (places?.[active]) select(places[active]);
          }
        }}
        className="mt-1 w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 text-sm"
      />
      <p id={hintId} className="mt-1 leading-relaxed text-[var(--kundali-muted)]">{labels.hint}</p>
      <p role="status" className="leading-relaxed text-[var(--kundali-muted)]">
        {expanded && searchable && (!current ? labels.loading :
          current.failed ? labels.failed : !places?.length ? labels.empty : null)}
      </p>
      {showOptions && (
        <ul id={listId} role="listbox" aria-label={label}
          className="mt-1 max-h-64 overflow-y-auto rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)]">
          {places?.map((place, index) => (
            <li key={place.id} id={`${listId}-${index}`} role="option" aria-selected={active === index}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => select(place)}
              className="min-h-11 cursor-pointer break-words border-b border-[var(--kundali-border-subtle)] px-3 py-2 last:border-0 hover:bg-[var(--kundali-strip)] aria-selected:bg-[var(--kundali-strip)]">
              <span className="block text-sm font-semibold">
                {locale === "ne" && place.devanagari_names.length > 0 && (
                  <>{place.devanagari_names.find((name) => name === query) ?? place.devanagari_names[0]} · </>
                )}
                {place.name}
              </span>
              <span className="block leading-relaxed text-[var(--kundali-muted)]">
                {place.context && `${place.context} · `}{place.latitude}, {place.longitude}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
