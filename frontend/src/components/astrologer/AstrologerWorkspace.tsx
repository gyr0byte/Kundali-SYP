"use client";

import Link from "next/link";
import { useEffect, useEffectEvent, useRef, useState, type FormEvent } from "react";
import { useAuthSession } from "@/components/auth/AuthSessionProvider";
import en from "@/i18n/astrologer.en.json";
import ne from "@/i18n/astrologer.ne.json";
import commonEn from "@/i18n/en.json";
import commonNe from "@/i18n/ne.json";
import {
  astrologerIssue, submitAstrologerApplication, validateApplication, verifyReviewAccess,
  type AstrologerApplication,
} from "@/lib/api/astrologer";
import { classifyLogoutAllOutcome, classifyLogoutOutcome, type LogoutOutcomeBanner } from "@/lib/auth/ui-helpers";
import type { AuthSessionUser } from "@/lib/auth/session-client";
import type { Locale } from "@/lib/kundali/types";

const dictionaries = { en, ne } satisfies Record<Locale, typeof en>;
const common = { en: commonEn.userWorkspace, ne: commonNe.userWorkspace };
const button = "inline-flex min-h-11 items-center rounded border border-[var(--kundali-border)] bg-white px-3 py-2 text-sm font-semibold text-[var(--kundali-navy)] hover:bg-[var(--kundali-strip)] disabled:opacity-60";
const primary = "inline-flex min-h-11 items-center justify-center rounded bg-[var(--kundali-navy)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--kundali-navy-hover)] disabled:opacity-60";
const sheet = "min-w-0 rounded border border-[var(--kundali-border)] bg-white p-4 sm:p-6";
const note = "text-sm leading-relaxed text-[var(--kundali-muted)]";
const sectionTitle = "text-lg font-semibold text-[var(--kundali-navy)]";
const signIn = "/login?redirect=%2Fastrologer";
const fields = ["display_name", "tradition", "credentials"] as const;
const blankApplication = { display_name: "", tradition: "", credentials: "" };

type Section = "review" | "profile" | "planned";
type QueueState = "loading" | "verified" | "auth" | "forbidden" | "unavailable";
type ApplicationState =
  | { status: "idle" | "sending" | "duplicate" }
  | { status: "auth" | "forbidden" | "validation" | "unavailable" }
  | { status: "pending"; profile: AstrologerApplication };

function AccountDisclosure({ locale, onFeedback }: {
  locale: Locale;
  onFeedback: (outcome: LogoutOutcomeBanner) => void;
}) {
  const auth = useAuthSession();
  const t = dictionaries[locale];
  const labels = common[locale];
  const disclosure = useRef<HTMLDetailsElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (confirm) cancel.current?.focus();
  }, [confirm]);

  function close() {
    if (disclosure.current) {
      disclosure.current.open = false;
      disclosure.current.querySelector("summary")?.focus();
    }
    setConfirm(false);
  }

  async function logout(all: boolean) {
    setBusy(true);
    try {
      onFeedback(all
        ? classifyLogoutAllOutcome(await auth.logoutAll(), labels)
        : classifyLogoutOutcome(await auth.logout(), labels));
    } finally {
      setBusy(false);
      close();
    }
  }

  return (
    <details ref={disclosure} className="group/account relative" onToggle={(event) => {
      if (!event.currentTarget.open) setConfirm(false);
    }} onKeyDown={(event) => {
      if (event.key === "Escape" && disclosure.current?.open) {
        event.stopPropagation();
        close();
      }
    }}>
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded border border-white/35 px-2.5 text-xs font-semibold hover:bg-white/10 [&::-webkit-details-marker]:hidden">
        {t.account}<span aria-hidden="true">⌄</span>
      </summary>
      <div className="absolute top-full right-0 z-30 mt-2 hidden w-[min(19rem,calc(100vw-1.5rem))] rounded border border-[var(--kundali-border)] bg-white p-2 text-[var(--kundali-ink)] shadow-lg group-open/account:block">
        <p className="border-b border-[var(--kundali-border)] p-2 text-sm font-semibold [overflow-wrap:anywhere]">{auth.user?.email}</p>
        {confirm ? (
          <div role="group" aria-label={labels.logoutConfirmTitle} className="space-y-2 p-2">
            <p className="text-sm font-semibold text-[var(--kundali-crimson)]">{labels.logoutConfirmTitle}</p>
            <p className={note}>{labels.logoutConfirmBody}</p>
            <div className="flex flex-wrap gap-2">
              <button ref={cancel} type="button" className={button} disabled={busy} onClick={close}>{labels.logoutConfirmCancel}</button>
              <button type="button" className={primary} disabled={busy} onClick={() => void logout(true)}>{labels.logoutConfirmProceed}</button>
            </div>
          </div>
        ) : (
          <div className="grid">
            <button type="button" disabled={busy} onClick={() => void logout(false)} className="min-h-11 rounded px-2 text-start text-sm hover:bg-[var(--kundali-strip)]">{busy ? labels.signingOutButton : labels.signOutButton}</button>
            <button type="button" disabled={busy} onClick={() => setConfirm(true)} className="min-h-11 rounded px-2 text-start text-sm text-[var(--kundali-crimson)] hover:bg-[var(--kundali-crimson-bg)]">{labels.signOutAllButton}</button>
          </div>
        )}
      </div>
    </details>
  );
}

function PlannedReview({ t }: { t: typeof en }) {
  return (
    <section className={sheet}>
      <h2 className={sectionTitle}>{t.reviewProcess}</h2>
      <ol className="mt-3 grid divide-y divide-[var(--kundali-border-subtle)] md:grid-cols-3 md:divide-x md:divide-y-0">
        {[[t.facts, t.factsBody], [t.sources, t.sourcesBody], [t.interpretation, t.interpretationBody]].map(([name, copy], index) => (
          <li key={name} className="flex gap-3 py-3 md:px-4 md:first:pl-0 md:last:pr-0">
            <span aria-hidden="true" className="font-mono text-xs leading-6 text-[var(--kundali-muted)]">0{index + 1}</span>
            <div><h3 className="font-semibold">{name}</h3><p className={note}>{copy}</p></div>
          </li>
        ))}
      </ol>
      <p className="mt-3 border-t border-[var(--kundali-border-subtle)] pt-3 text-sm text-[var(--kundali-muted)]">{t.privacy}</p>
    </section>
  );
}

function AuthenticatedWorkspace({ user, section, locale, openSection }: {
  user: AuthSessionUser;
  section: Section;
  locale: Locale;
  openSection: (section: Section) => void;
}) {
  const auth = useAuthSession();
  const t = dictionaries[locale];
  const labels = common[locale];
  const [attempt, setAttempt] = useState(0);
  const [queue, setQueue] = useState<QueueState>("loading");
  const [application, setApplication] = useState<ApplicationState>({ status: "idle" });
  const [draft, setDraft] = useState<AstrologerApplication>(blankApplication);
  const [errors, setErrors] = useState({ display_name: false, credentials: false, tradition: false });
  const submission = useRef<AbortController | null>(null);
  const checkAccess = useEffectEvent((signal: AbortSignal) => verifyReviewAccess(auth, signal));

  useEffect(() => {
    const request = new AbortController();
    void checkAccess(request.signal).then(() => {
      if (!request.signal.aborted) setQueue("verified");
    }).catch((error: unknown) => {
      if (request.signal.aborted) return;
      const issue = astrologerIssue(error);
      setQueue(issue === "auth" || issue === "forbidden" ? issue : "unavailable");
    });
    return () => request.abort();
  }, [attempt]);

  useEffect(() => () => submission.current?.abort(), []);

  function retry() {
    setQueue("loading");
    setAttempt((count) => count + 1);
  }

  const applicationAllowed = user.role === "user" && (queue === "forbidden" || queue === "unavailable");

  async function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submission.current || !applicationAllowed) return;
    const { errors: invalid } = validateApplication(draft);
    setErrors(invalid);
    if (fields.some((field) => invalid[field])) {
      event.currentTarget.querySelector<HTMLElement>(`#astrologer-${fields.find((field) => invalid[field])}`)?.focus();
      return;
    }
    const request = new AbortController();
    submission.current = request;
    setApplication({ status: "sending" });
    try {
      const profile = await submitAstrologerApplication(auth, user.id, draft, request.signal);
      if (!request.signal.aborted) {
        setApplication({ status: "pending", profile });
        setDraft(blankApplication);
      }
    } catch (error) {
      if (!request.signal.aborted) {
        setApplication({ status: astrologerIssue(error) });
      }
    } finally {
      if (submission.current === request) submission.current = null;
    }
  }

  if (section === "planned") return <PlannedReview t={t} />;

  const retryButton = <button type="button" className={button} onClick={retry} disabled={queue === "loading"}>{t.checkAgain}</button>;
  const accessStatus = queue === "loading" ? (
    <p role="status" className={note}>{t.checkingAccess}</p>
  ) : queue === "verified" ? (
    <p role="status" className="inline-flex w-fit rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-2.5 py-1 text-xs font-semibold text-[var(--kundali-emerald)]">{t.accessVerified}</p>
  ) : queue === "forbidden" ? (
    <p role="status" className={note}>{user.role === "user" ? t.accessDeniedBody : t.standingUnknown}</p>
  ) : (
    <p role="alert" className="text-sm text-[var(--kundali-crimson)]">{queue === "auth" ? t.expired : t.accessError}</p>
  );
  const accessActions = queue !== "loading" && (
    <div className="mt-4 flex flex-wrap gap-2">
      {queue === "auth" ? <Link href={signIn} className={primary}>{labels.signInNavButton}</Link> : retryButton}
      {section === "review" && queue === "forbidden" && user.role === "user" ? (
        <button type="button" className={primary} onClick={() => openSection("profile")}>{t.goToApplication}</button>
      ) : null}
    </div>
  );

  if (section === "review") {
    return (
      <div className="space-y-4">
        <section className={sheet}>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-[var(--kundali-border)] pb-3">
            <h2 className={sectionTitle}>{t.reviewQueue}</h2>
            {queue === "verified" ? accessStatus : null}
          </div>
          {queue === "verified" ? (
            <div className="max-w-xl py-4">
              <h3 className="font-semibold text-[var(--kundali-navy)]">{t.queueStub}</h3>
              <p className={`mt-1 ${note}`}>{t.queueStubBody}</p>
            </div>
          ) : (
            <div>
              {queue === "forbidden" ? <h3 className="mb-1 font-semibold">{t.accessDenied}</h3> : null}
              {accessStatus}
            </div>
          )}
          {accessActions}
        </section>
        {queue === "verified" ? <PlannedReview t={t} /> : null}
      </div>
    );
  }

  const fieldText = {
    display_name: [t.displayName, t.nameError],
    tradition: [t.tradition, t.traditionError],
    credentials: [t.credentials, t.credentialsError],
  };
  const submitErrors = {
    auth: t.expired, forbidden: t.applicationForbidden, validation: t.validation, unavailable: t.applicationError,
  };
  const submitError = application.status === "idle" || application.status === "sending" ||
    application.status === "pending" || application.status === "duplicate"
    ? null : submitErrors[application.status];
  return (
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(17rem,1fr)]">
      <section className={sheet}>
        {application.status === "pending" ? (
          <>
            <h2 className={sectionTitle}>{t.pending}</h2>
            <p role="status" className={`mt-2 ${note}`}>{t.pendingBody}</p>
            <dl className="mt-4 divide-y divide-[var(--kundali-border-subtle)] border-y border-[var(--kundali-border-subtle)] text-sm">
              {fields.map((field) => <div className="py-2.5" key={field}>
                <dt className="font-semibold">{fieldText[field][0]}</dt>
                <dd className="whitespace-pre-wrap [overflow-wrap:anywhere]">{application.profile[field]}</dd>
              </div>)}
            </dl>
          </>
        ) : application.status === "duplicate" ? (
          <p role="status" className={note}>{t.duplicate}</p>
        ) : applicationAllowed ? (
          <>
            <h2 className={sectionTitle}>{t.application}</h2>
            <p className={`mt-1 ${note}`}>{t.applicationBody}</p>
            <form className="mt-5 space-y-4" noValidate onSubmit={(event) => void apply(event)}>
              {fields.map((field) => {
                const id = `astrologer-${field}`;
                const props = {
                  id, name: field, value: draft[field], required: true,
                  disabled: application.status === "sending",
                  "aria-invalid": errors[field],
                  "aria-describedby": [field === "credentials" ? "credential-hint" : "", errors[field] ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined,
                  className: "mt-1 block min-h-11 w-full rounded border border-[var(--kundali-border)] px-3 py-2 text-base aria-invalid:border-[var(--kundali-crimson)]",
                };
                return (
                  <div key={field}>
                    <label htmlFor={id} className="text-sm font-semibold">{fieldText[field][0]}</label>
                    {field === "credentials" ? (
                      <><p id="credential-hint" className={note}>{t.credentialHint}</p>
                        <textarea {...props} rows={4} onChange={(event) => setDraft({ ...draft, credentials: event.target.value })} />
                      </>
                    ) : <input {...props} type="text" onChange={(event) => setDraft({ ...draft, [field]: event.target.value })} />}
                    {errors[field] ? <p id={`${id}-error`} role="alert" className="mt-1 text-sm text-[var(--kundali-crimson)]">{fieldText[field][1]}</p> : null}
                  </div>
                );
              })}
              {submitError ? (
                <p role="alert" className="text-sm text-[var(--kundali-crimson)]">{submitError}</p>
              ) : null}
              {application.status === "auth" ? (
                <Link href={signIn} className={primary}>{labels.signInNavButton}</Link>
              ) : (
                <button type="submit" className={primary} disabled={application.status === "sending"}>
                  {application.status === "sending" ? t.submitting : t.apply}
                </button>
              )}
              <p role="status" className="sr-only">{application.status === "sending" ? t.submitting : ""}</p>
            </form>
          </>
        ) : <p className={note}>{t.professionalUnavailable}</p>}
      </section>
      <section className={sheet}>
        <h2 className={sectionTitle}>{t.reviewQueue}</h2>
        <div className="mt-2">{accessStatus}</div>
        {accessActions}
        {user.role === "user" && queue !== "verified" ? <p className={`mt-4 border-t border-[var(--kundali-border)] pt-3 ${note}`}>{t.applicationStatusUnavailable}</p> : null}
      </section>
    </div>
  );
}

export function AstrologerWorkspace() {
  const auth = useAuthSession();
  const [locale, setLocale] = useState<Locale>("en");
  const [section, setSection] = useState<Section>("review");
  const [menuOpen, setMenuOpen] = useState(false);
  const [feedback, setFeedback] = useState<LogoutOutcomeBanner | null>(null);
  const main = useRef<HTMLElement>(null);
  const t = dictionaries[locale];
  const labels = common[locale];
  const titles = { review: t.review, profile: t.profile, planned: t.planned };

  function openSection(next: Section) {
    setSection(next);
    setMenuOpen(false);
    main.current?.focus();
  }

  return (
    <div lang={locale} className="flex min-h-screen flex-col bg-[var(--kundali-cream)] text-[var(--kundali-ink)]">
      <a href="#astrologer-main" className="sr-only focus:not-sr-only focus:absolute focus:z-40 focus:bg-white focus:px-4 focus:py-2">{t.skip}</a>
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
            {auth.user ? <AccountDisclosure key={auth.user.id} locale={locale} onFeedback={setFeedback} /> : null}
          </div>
        </div>
      </header>
      <div className="mx-auto grid w-full max-w-[1600px] flex-1 grid-rows-[auto_1fr] lg:grid-cols-[230px_minmax(0,1fr)] lg:grid-rows-1">
        <aside className="border-b border-[var(--kundali-border)] bg-[var(--kundali-strip)] px-4 py-2.5 lg:border-r lg:border-b-0 lg:px-5 lg:py-8">
          <button type="button" aria-expanded={menuOpen} aria-controls="astrologer-navigation" onClick={() => setMenuOpen((open) => !open)} className={`${button} w-full justify-between gap-2 lg:hidden`}>
            {t.menu}<span aria-hidden="true">{menuOpen ? "−" : "+"}</span>
          </button>
          <nav id="astrologer-navigation" aria-label={t.navigation} className={menuOpen ? "mt-3" : "hidden lg:block"}>
            <p className="mb-3 px-3 text-sm font-semibold text-[var(--kundali-muted)]">{t.title}</p>
            {(["review", "profile", "planned"] as const).map((item) => (
              <button type="button" key={item} aria-current={section === item ? "page" : undefined}
                onClick={() => openSection(item)}
                className={`mb-1 block min-h-11 w-full rounded border px-3 py-2 text-start text-sm font-semibold ${section === item ? "border-[var(--kundali-border)] bg-white" : "border-transparent hover:bg-[var(--kundali-cream)]"}`}>
                {titles[item]}
              </button>
            ))}
          </nav>
        </aside>
        <main id="astrologer-main" ref={main} tabIndex={-1} className="min-w-0 px-4 pt-6 pb-10 sm:px-6 sm:pt-8 xl:px-8">
          <div className="mb-5 border-b border-[var(--kundali-border)] pb-4">
            <h1 className={`text-3xl leading-tight text-[var(--kundali-navy)] sm:text-[2.65rem] ${locale === "en" ? "font-serif tracking-tight" : ""}`}>{titles[section]}</h1>
            {section !== "planned" ? <p className={`mt-2 ${note}`}>{section === "review" ? t.reviewIntro : t.profileIntro}</p> : null}
          </div>
          {feedback ? <p role="status" className={`${sheet} mb-4 text-sm ${feedback.tone === "crimson" ? "text-[var(--kundali-crimson)]" : ""}`}>{feedback.message}</p> : null}
          {auth.status === "authenticated" && auth.user ? (
            <AuthenticatedWorkspace key={`${auth.user.id}:${auth.user.role}`} user={auth.user} section={section} locale={locale} openSection={openSection} />
          ) : auth.status === "checking" ? (
            <p className={sheet} role="status">{t.checking}</p>
          ) : auth.status === "unavailable" ? (
            <div className={sheet}><p role="alert" className={note}>{t.sessionUnavailable}</p><button type="button" onClick={() => void auth.retrySession()} className={`${button} mt-3`}>{labels.retrySessionButton}</button></div>
          ) : (
            <section className={sheet}>
              <h2 className={sectionTitle}>{t.signedOut}</h2>
              <p className={`mt-2 ${note}`}>{t.signedOutBody}</p>
              <div className="mt-4 flex flex-wrap gap-2"><Link href={signIn} className={primary}>{labels.signInNavButton}</Link><Link href="/register" className={button}>{labels.createAccountNavButton}</Link></div>
            </section>
          )}
          {section === "planned" && (
            <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-[var(--kundali-border)] pt-3 text-sm text-[var(--kundali-muted)]">
              <li>{t.knowledge}</li><li>{t.activity}</li>
            </ul>
          )}
        </main>
      </div>
      <footer className="border-t border-[var(--kundali-border)] bg-[var(--kundali-strip)] px-4 py-3 text-xs leading-relaxed text-[var(--kundali-muted)] sm:px-6">
        <p className="mx-auto max-w-[1552px]">{t.disclaimer}</p>
      </footer>
    </div>
  );
}
