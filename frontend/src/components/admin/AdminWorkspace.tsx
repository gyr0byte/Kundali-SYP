"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useAuthSession } from "@/components/auth/AuthSessionProvider";
import { WorkspaceAccountDisclosure } from "@/components/auth/WorkspaceAccountDisclosure";
import { AdminDataView, adminButton, adminSheet, type AdminMessages, type AdminSection } from "./AdminDataView";
import en from "@/i18n/admin.en.json";
import ne from "@/i18n/admin.ne.json";
import commonEn from "@/i18n/en.json";
import commonNe from "@/i18n/ne.json";
import type { LogoutOutcomeBanner } from "@/lib/auth/ui-helpers";
import type { Locale } from "@/lib/kundali/types";

const messages = { en, ne } satisfies Record<Locale, AdminMessages>;
const common = { en: commonEn.userWorkspace, ne: commonNe.userWorkspace };
const sections = ["overview", "users", "astrologers", "audit", "planned"] as const;
const signIn = "/login?redirect=%2Fadmin";

export function AdminWorkspace() {
  const auth = useAuthSession();
  const [locale, setLocale] = useState<Locale>("en");
  const [feedback, setFeedback] = useState<LogoutOutcomeBanner | null>(null);
  return <AdminConsole key={`${auth.status}:${auth.user?.id}:${auth.user?.role}`}
    locale={locale} setLocale={setLocale} feedback={feedback} setFeedback={setFeedback} />;
}

function AdminConsole({ locale, setLocale, feedback, setFeedback }: {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  feedback: LogoutOutcomeBanner | null;
  setFeedback: (feedback: LogoutOutcomeBanner) => void;
}) {
  const auth = useAuthSession();
  const [section, setSection] = useState<AdminSection>("overview");
  const [menuOpen, setMenuOpen] = useState(false);
  const [denied, setDenied] = useState<"expired" | "forbidden" | null>(null);
  const main = useRef<HTMLElement>(null);
  const t = messages[locale];
  const labels = common[locale];
  const admin = auth.status === "authenticated" && auth.user?.role === "admin" ? auth.user : null;
  const allowed = Boolean(admin && !denied);
  const title = allowed ? t[section] : t.title;
  const intro = section === "planned" ? null : t[`${section}Intro`];

  function navigate(next: AdminSection) {
    setSection(next);
    setMenuOpen(false);
    main.current?.focus();
  }

  return (
    <div lang={locale} className="flex min-h-screen flex-col bg-[var(--kundali-cream)] text-[var(--kundali-ink)]">
      <a href="#admin-main" className="sr-only focus:not-sr-only focus:absolute focus:z-40 focus:bg-white focus:px-4 focus:py-2">{t.skip}</a>
      <header className="bg-[var(--kundali-navy)] px-3 text-white sm:px-6">
        <div className="mx-auto flex min-h-16 max-w-[1600px] items-center justify-between gap-2">
          <Link href="/" className="inline-flex min-h-11 items-center gap-2">
            <svg width="27" height="27" viewBox="0 0 36 36" fill="none" stroke="currentColor" aria-hidden="true">
              <circle cx="18" cy="18" r="15" /><path d="M18 3 33 18 18 33 3 18Z M10 10l16 16m0-16L10 26" /><circle cx="18" cy="18" r="4" />
            </svg>
            <span className="font-serif text-xl font-semibold">{labels.brandName}</span>
            <span lang="ne" className="hidden text-xs text-white/85 sm:inline">{labels.brandNative}</span>
          </Link>
          <div className="flex items-center gap-2 sm:gap-4">
            <div role="group" aria-label={t.language} className="flex rounded border border-white/35">
              {(["en", "ne"] as const).map((language) => (
                <button key={language} type="button" lang={language} aria-pressed={locale === language}
                  onClick={() => setLocale(language)}
                  className={`min-h-11 px-2 text-xs font-semibold sm:px-3 ${locale === language ? "bg-[var(--kundali-cream)] text-[var(--kundali-navy)]" : "hover:bg-white/10"}`}>
                  {language === "en" ? "EN" : "नेपाली"}
                </button>
              ))}
            </div>
            {auth.user ? <WorkspaceAccountDisclosure locale={locale} label={t.account} onFeedback={setFeedback} /> : null}
          </div>
        </div>
      </header>
      <div className={`mx-auto grid w-full max-w-[1600px] flex-1 ${allowed ? "grid-rows-[auto_1fr] lg:grid-cols-[230px_minmax(0,1fr)] lg:grid-rows-1" : ""}`}>
        {allowed ? (
          <aside className="border-b border-[var(--kundali-border)] bg-[var(--kundali-strip)] px-4 py-2.5 lg:border-r lg:border-b-0 lg:px-5 lg:py-8">
            <button type="button" aria-expanded={menuOpen} aria-controls="admin-navigation" onClick={() => setMenuOpen((open) => !open)} className={`${adminButton} w-full justify-between gap-2 lg:hidden`}>
              {t.menu}<span aria-hidden="true">{menuOpen ? "−" : "+"}</span>
            </button>
            <nav id="admin-navigation" aria-label={t.navigation} className={menuOpen ? "mt-3" : "hidden lg:block"}>
              <p className="mb-3 px-3 text-sm font-semibold text-[var(--kundali-muted)]">{t.title}</p>
              {sections.map((item) => (
                <button type="button" key={item} aria-current={section === item ? "page" : undefined}
                  onClick={() => navigate(item)}
                  className={`mb-1 block min-h-11 w-full rounded border px-3 py-2 text-start text-sm font-semibold ${section === item ? "border-[var(--kundali-border)] bg-white" : "border-transparent hover:bg-[var(--kundali-cream)]"} ${item === "planned" ? "mt-5" : ""}`}>
                  {t[item]}
                </button>
              ))}
            </nav>
          </aside>
        ) : null}
        <main id="admin-main" ref={main} tabIndex={-1} className={`w-full min-w-0 px-4 pt-6 pb-10 sm:px-6 sm:pt-8 xl:px-8 ${allowed ? "" : "mx-auto max-w-4xl"}`}>
          <div className="mb-5 border-b border-[var(--kundali-border)] pb-4">
            <h1 className={`text-3xl leading-tight text-[var(--kundali-navy)] sm:text-[2.65rem] ${locale === "en" ? "font-serif tracking-tight" : ""}`}>{title}</h1>
            {allowed && intro ? <p className="mt-2 text-sm leading-relaxed text-[var(--kundali-muted)]">{intro}</p> : null}
          </div>
          {feedback ? <p role="status" className={`${adminSheet} mb-4 p-4 text-sm`}>{feedback.message}</p> : null}
          {allowed && admin ? (
            section === "planned" ? (
              <ul className={`${adminSheet} divide-y divide-[var(--kundali-border)] px-4`}>
                {[t.calculation, t.quality, t.knowledge, t.moderation].map((feature) => (
                  <li key={feature} className="flex flex-wrap items-center justify-between gap-2 py-3">
                    <strong>{feature}</strong><span className="text-sm text-[var(--kundali-muted)]">{t.unavailable}</span>
                  </li>
                ))}
              </ul>
            ) : <AdminDataView key={section} section={section} actorId={admin.id} locale={locale} t={t} onDenied={setDenied} />
          ) : (
            <section className={`${adminSheet} space-y-3 p-4 sm:p-6`}>
              {auth.status === "checking" ? <p role="status">{t.checking}</p> : null}
              {auth.status === "unavailable" ? (
                <><p role="alert">{t.sessionError}</p><button type="button" className={adminButton} onClick={() => void auth.retrySession()}>{t.retry}</button></>
              ) : null}
              {auth.status === "unauthenticated" || denied === "expired" ? (
                <><h2 className="text-lg font-semibold">{t.signedOut}</h2><p>{denied === "expired" ? t.expired : t.signedOutBody}</p><Link href={signIn} className={adminButton}>{labels.signInNavButton}</Link></>
              ) : null}
              {auth.status === "authenticated" && (denied === "forbidden" || !admin) ? (
                <><p role="alert">{t.forbidden}</p>{admin ? <button type="button" className={adminButton} onClick={() => { setDenied(null); navigate("overview"); }}>{t.retry}</button> : null}</>
              ) : null}
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
