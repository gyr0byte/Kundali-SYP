import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Suspense } from "react";
import sage from "../../public/image/vedic-sage.webp";
import en from "@/i18n/landing.en.json";
import ne from "@/i18n/landing.ne.json";
import { getPlacementFacts } from "@/lib/kundali/chart-helpers";
import { PLANET_LABELS, ZODIAC_SIGNS } from "@/lib/kundali/constants";
import { SAMPLE_NORTH_LONDON_CHART_FACTS as sample } from "@/lib/kundali/sample-north-london";
import type { Locale } from "@/lib/kundali/types";
import "./landing.css";

const messages = { en, ne } satisfies Record<Locale, typeof en>;

type LocaleParams = Pick<PageProps<"/">, "searchParams">;

async function resolveLocale(searchParams: LocaleParams["searchParams"]): Promise<Locale> {
  return (await searchParams).lang === "ne" ? "ne" : "en";
}

export async function generateMetadata({ searchParams }: LocaleParams): Promise<Metadata> {
  const { metaTitle: title, metaDescription: description } = messages[await resolveLocale(searchParams)];
  return { title, description, openGraph: { type: "website", title, description } };
}

const placements = getPlacementFacts(sample);
const houseLabels = [
  [180, 91], [91, 41], [42, 91], [90, 180], [42, 270], [91, 319],
  [180, 269], [269, 319], [318, 270], [270, 180], [318, 91], [269, 41],
];

function Brand() {
  return (
    <a className="observatory-brand" href="#top" aria-label="Kundali">
      <svg viewBox="0 0 36 36" width="34" height="34" aria-hidden="true">
        <g fill="none" stroke="currentColor">
          <circle cx="18" cy="18" r="15" />
          <path d="M18 3 33 18 18 33 3 18Z M10 10l16 16m0-16L10 26" />
          <circle cx="18" cy="18" r="4" />
        </g>
      </svg>
      <span>Kundali <small lang="ne">कुण्डली</small></span>
    </a>
  );
}

function RegisterLink({ children }: { children: string }) {
  return (
    <Link href="/register" className="observatory-button">
      {children}<span aria-hidden="true">↗</span>
    </Link>
  );
}

function SagePlate() {
  return (
    <div className="observatory-plate">
      <svg className="observatory-orbit" viewBox="0 0 800 610" aria-hidden="true" fill="none">
        <g stroke="currentColor">
          <circle cx="400" cy="305" r="234" />
          <circle cx="400" cy="305" r="266" />
          <circle cx="400" cy="305" r="277" strokeDasharray="1 9" strokeWidth="4" />
          <path d="M64 305h672M400 12v586M216 121l368 368m-368 0 368-368" opacity=".5" />
          <ellipse cx="400" cy="305" rx="330" ry="124" transform="rotate(-24 400 305)" />
          <circle cx="231" cy="102" r="5" fill="currentColor" />
          <circle cx="656" cy="241" r="4" fill="currentColor" />
          <circle cx="121" cy="405" r="4" fill="currentColor" />
        </g>
      </svg>
      <Image
        className="observatory-sage"
        src={sage}
        alt=""
        sizes="(max-width: 640px) 100vw, (max-width: 1440px) 52vw, 750px"
        loading="eager"
        fetchPriority="high"
      />
    </div>
  );
}

function SampleChart({ locale }: { locale: Locale }) {
  const t = messages[locale];
  const selected = placements.filter(({ planet }) => ["Sun", "Moon", "Jupiter", "Saturn"].includes(planet));

  return (
    <figure className="observatory-specimen">
      <figcaption>
        <span>{t.sampleLabel}</span><time dateTime="2015-05-15">{t.sampleDate}</time>
      </figcaption>
      <div className="observatory-specimen-body">
        <svg className="observatory-chart-drawing" viewBox="0 0 360 360" role="img" aria-labelledby="sample-diagram-title sample-diagram-desc">
          <title id="sample-diagram-title">{t.chartDiagram}</title>
          <desc id="sample-diagram-desc">
            {t.ascendant}. {placements.map(({ planet, house }) =>
              `${locale === "ne" ? PLANET_LABELS[planet]?.ne ?? planet : planet} ${house}`
            ).join(", ")}
          </desc>
          <rect x="5" y="5" width="350" height="350" fill="none" stroke="currentColor" />
          <path d="M5 5 355 355M355 5 5 355M180 5 355 180 180 355 5 180Z" fill="none" stroke="currentColor" opacity=".55" />
          {houseLabels.map(([x, y], index) => {
            const house = index + 1;
            const labels = placements.filter((fact) => fact.house === house).map(({ planet }) =>
              locale === "ne" ? PLANET_LABELS[planet]?.glyphNe ?? planet : planet.slice(0, 2)
            );
            return (
              <g key={house} textAnchor="middle">
                <text x={x} y={y - 14} className="observatory-house">{house}</text>
                <text x={x} y={y + 7}>{house === 1 ? t.ascendantShort : labels.join(" · ")}</text>
              </g>
            );
          })}
        </svg>
        <table>
          <caption>{t.placements}</caption>
          <thead><tr><th scope="col">{t.body}</th><th scope="col">{t.sign}</th><th scope="col">{t.degree}</th></tr></thead>
          <tbody>
            {selected.map((fact) => (
              <tr key={fact.id}>
                <th scope="row">{locale === "ne" ? PLANET_LABELS[fact.planet]?.ne ?? fact.planet : fact.planet}</th>
                <td>{locale === "ne" ? ZODIAC_SIGNS[fact.sign_index]?.ne ?? fact.sign : fact.sign}</td>
                <td>{fact.degree.toFixed(2)}°</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="observatory-sample-meta">{t.sampleMethod}</p>
    </figure>
  );
}

function Observatory({ locale }: { locale: Locale }) {
  const t = messages[locale];

  return (
    <div id="top" lang={locale} className="observatory-landing">
      <a href="#main" className="observatory-skip">{t.skip}</a>
      <header className="observatory-header">
        <div className="observatory-wrap observatory-shell">
          <Brand />
          <nav className="observatory-navigation" aria-label={t.sections}>
            <a href="#chart">{t.sampleNav}</a>
            <a href="#process">{t.processNav}</a>
            <a href="#method">{t.methodNav}</a>
          </nav>
          <div className="observatory-account">
            <nav className="observatory-languages" aria-label={t.language}>
              <Link href="/" lang="en" hrefLang="en" aria-current={locale === "en" ? "page" : undefined}>EN</Link>
              <Link href="/?lang=ne" lang="ne" hrefLang="ne" aria-current={locale === "ne" ? "page" : undefined}>नेपाली</Link>
            </nav>
            <Link href="/login">{t.signIn}</Link>
            <RegisterLink>{t.register}</RegisterLink>
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <section className="observatory-hero" aria-labelledby="observatory-title">
          <div className="observatory-wrap observatory-hero-inner">
            <div className="observatory-hero-copy">
              <h1 id="observatory-title">{t.headline}<br /><em>{t.headlineAccent}</em></h1>
              <p>{t.intro}</p>
              <div className="observatory-actions">
                <RegisterLink>{t.createChart}</RegisterLink>
                <a href="#chart" className="observatory-text-link">{t.explore} <span aria-hidden="true">↓</span></a>
              </div>
            </div>
            <SagePlate />
          </div>
        </section>
        <section id="chart" className="observatory-section">
          <div className="observatory-wrap observatory-chart-layout">
            <div className="observatory-chart-intro">
              <h2>{t.chartTitle}<br />{t.chartTitleSecond}</h2>
              <p>{t.chartIntro}</p>
            </div>
            <SampleChart locale={locale} />
          </div>
        </section>
        <section id="process" className="observatory-section observatory-process">
          <div className="observatory-wrap">
            <h2>{t.processTitle}</h2>
            <ol>
              {t.steps.map(({ title, detail }, index) => (
                <li key={title}>
                  <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                  <div><h3>{title}</h3><p>{detail}</p></div>
                </li>
              ))}
            </ol>
          </div>
        </section>
        <section id="method" className="observatory-section">
          <div className="observatory-wrap observatory-method-layout">
            <h2>{t.methodTitle}</h2>
            <dl>
              {t.method.map(({ title, detail }) => (
                <div key={title}><dt>{title}</dt><dd>{detail}</dd></div>
              ))}
            </dl>
            <p className="observatory-planned">{t.planned}</p>
          </div>
        </section>
        <section className="observatory-section observatory-end">
          <div className="observatory-wrap observatory-end-inner">
            <h2>{t.finalTitle}</h2>
            <RegisterLink>{t.createChart}</RegisterLink>
          </div>
        </section>
      </main>
      <footer className="observatory-footer">
        <div className="observatory-wrap observatory-footer-inner">
          <Brand />
          <p>{t.disclaimer}</p>
          <a href="#top">{t.backToTop} <span aria-hidden="true">↑</span></a>
        </div>
      </footer>
    </div>
  );
}

async function LocalizedObservatory({ searchParams }: LocaleParams) {
  return <Observatory locale={await resolveLocale(searchParams)} />;
}

export default function Home({ searchParams }: PageProps<"/">) {
  return (
    <Suspense>
      <LocalizedObservatory searchParams={searchParams} />
    </Suspense>
  );
}
