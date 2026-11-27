import { NAKSHATRA_NE, ZODIAC_SIGNS } from "@/lib/kundali/constants";
import type { Locale, MoonValues, MoonWindow } from "@/lib/kundali/types";

export interface MoonWindowLabels {
  title: string;
  explanation: string;
  limits: string;
  sign: string;
  nakshatra: string;
  pada: string;
  stable: string;
  uncertain: string;
  unavailable: string;
  hours: string;
  duration: string;
  calculate: string;
  recalculate: string;
  calculated: string;
}

export function MoonWindowPanel({
  result, labels, locale,
}: { result: MoonWindow | null; labels: MoonWindowLabels; locale: Locale }) {
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 4 });
  const mansion = (name: string) => locale === "ne" ? (NAKSHATRA_NE[name] ?? name) : name;
  const rows: { label: string; category: MoonValues<unknown>; names: string[] }[] = result ? [
    {
      label: labels.sign,
      category: result.signs,
      names: result.signs.possible.flatMap(index => {
        const sign = ZODIAC_SIGNS[index];
        return sign ? [sign[locale]] : [];
      }),
    },
    { label: labels.nakshatra, category: result.nakshatras, names: result.nakshatras.possible.map(mansion) },
    {
      label: labels.pada, category: result.padas,
      names: result.padas.possible.map(({ nakshatra, pada }) => `${mansion(nakshatra)} · ${number.format(pada)}`),
    },
  ] : [];

  return (
    <section aria-labelledby="moon-window-heading"
      className="space-y-3 rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] p-4">
      <h2 id="moon-window-heading" className="font-semibold text-[var(--kundali-navy)]">{labels.title}</h2>
      <p className="text-sm leading-relaxed text-[var(--kundali-muted)]">{labels.explanation}</p>
      {result && (
        <>
          <p className="text-sm text-[var(--kundali-muted)]">
            {labels.duration} <span className="tabular-data font-semibold">{number.format(result.duration_seconds / 3600)} {labels.hours}</span>
          </p>
          <dl className="divide-y divide-[var(--kundali-border-subtle)] border-y border-[var(--kundali-border-subtle)]">
            {rows.map(({ label, category, names }) => (
              <div key={label} className="grid gap-1 py-3 sm:grid-cols-[minmax(8rem,1fr)_minmax(0,3fr)]">
                <dt className="font-semibold text-[var(--kundali-navy)]">{label}</dt>
                <dd className="min-w-0 text-sm leading-relaxed">
                  <span className="block font-semibold">{labels[category.status]}</span>
                  {names.length > 0 && <span className="break-words">{names.join(", ")}</span>}
                </dd>
              </div>
            ))}
          </dl>
          <p className="text-xs leading-relaxed text-[var(--kundali-muted)]">{labels.limits}</p>
        </>
      )}
    </section>
  );
}
