"use client";

import Link from "next/link";
import React, { useEffect, useRef, useState } from "react";
import { useAuthSession } from "@/components/auth/AuthSessionProvider";
import { AuthPanelLayout } from "@/components/auth/AuthPanelLayout";
import { resolveSafePostLoginRedirect, validateLoginInputs } from "@/lib/auth/navigation";
import {
  resolveLocalizedAuthErrors,
  type AuthLocale,
  type AuthMessages,
} from "@/lib/auth/ui-helpers";

export interface LoginFormProps {
  messagesByLocale: Record<AuthLocale, AuthMessages>;
  initialLocale?: AuthLocale;
  redirectParam?: string | null;
  registeredParam?: string | null;
  onNavigate?: (href: string) => void;
}

export function LoginForm({
  messagesByLocale,
  initialLocale = "en",
  redirectParam = null,
  registeredParam = null,
  onNavigate,
}: LoginFormProps) {
  const session = useAuthSession();
  const [locale, setLocale] = useState<AuthLocale>(initialLocale);
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isRetryingSession, setIsRetryingSession] = useState<boolean>(false);
  const [errorMessages, setErrorMessages] = useState<string[]>([]);
  const [validationFieldError, setValidationFieldError] = useState<
    "emailInvalid" | "passwordRequired" | null
  >(null);

  const submitLockRef = useRef<boolean>(false);
  const t = messagesByLocale[locale];
  const safeDestination = resolveSafePostLoginRedirect(redirectParam);

  useEffect(() => {
    if (session.status === "authenticated" && onNavigate) {
      onNavigate(safeDestination);
    }
  }, [onNavigate, safeDestination, session.status]);

  async function handleRetrySession() {
    if (isRetryingSession || isSubmitting) {
      return;
    }
    setIsRetryingSession(true);
    setErrorMessages([]);
    try {
      const next = await session.retrySession();
      if (next.status === "authenticated") {
        setPassword("");
        onNavigate?.(safeDestination);
      } else if (next.status === "unavailable") {
        setErrorMessages([t.errorSessionRecovery]);
      }
    } finally {
      setIsRetryingSession(false);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting || submitLockRef.current || session.status === "checking") {
      return;
    }

    const validation = validateLoginInputs(email, password);
    if (validation.errorKey) {
      setValidationFieldError(validation.errorKey);
      setErrorMessages([]);
      return;
    }

    setValidationFieldError(null);
    setErrorMessages([]);
    submitLockRef.current = true;
    setIsSubmitting(true);

    try {
      const result = await session.login(validation.email, password);
      if (result.ok) {
        setPassword("");
        onNavigate?.(safeDestination);
        return;
      }
      if (result.code === "SESSION_RECOVERY_UNAVAILABLE") {
        // The unavailable session box renders errorSessionRecovery with Retry session.
        return;
      }
      setErrorMessages(resolveLocalizedAuthErrors(result, t));
    } finally {
      submitLockRef.current = false;
      setIsSubmitting(false);
    }
  }

  const displayedErrors = validationFieldError
    ? [
        validationFieldError === "emailInvalid"
          ? t.validationEmailInvalid
          : t.validationPasswordRequired,
      ]
    : errorMessages;

  const isChecking = session.status === "checking";
  const isUnavailable = session.status === "unavailable";
  const isFormBusy = isSubmitting || isRetryingSession;

  return (
    <AuthPanelLayout
      locale={locale}
      onLocaleChange={setLocale}
      messages={t}
      title={t.loginTitle}
      subtitle={t.loginSubtitle}
    >
      {isChecking ? (
        <div
          role="status"
          className="rounded border border-[var(--kundali-border)] bg-[var(--kundali-cream)] px-4 py-3 text-xs"
        >
          <p className="font-semibold text-[var(--kundali-navy)]">{t.checkingSessionTitle}</p>
          <p className="mt-1 leading-relaxed text-[var(--kundali-muted)]">
            {t.checkingSessionBody}
          </p>
        </div>
      ) : null}

      {!isChecking && isUnavailable ? (
        <div
          role="alert"
          className="mb-4 rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-4 py-3 text-xs"
        >
          <p className="font-semibold text-[var(--kundali-crimson)]">{t.unavailableTitle}</p>
          <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">
            {session.hasRecoverableSession ? t.errorSessionRecovery : t.unavailableBody}
          </p>
          <button
            type="button"
            disabled={isFormBusy}
            onClick={() => void handleRetrySession()}
            className="mt-3 inline-flex min-h-[40px] items-center rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-surface)] px-3.5 py-2 text-xs font-semibold text-[var(--kundali-crimson)] hover:bg-[var(--kundali-cream)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isRetryingSession ? t.retryingSessionButton : t.retrySessionButton}
          </button>
        </div>
      ) : null}

      {!isChecking && registeredParam === "1" && displayedErrors.length === 0 ? (
        <div
          role="status"
          className="mb-4 rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-3.5 py-2.5 text-xs font-medium text-[var(--kundali-emerald)]"
        >
          {t.registeredBanner}
        </div>
      ) : null}

      {!isChecking ? (
        <form onSubmit={handleSubmit} className="space-y-4 text-xs" noValidate>
          {displayedErrors.length > 0 ? (
            <div
              id="login-form-error"
              role="alert"
              className="rounded border border-[var(--kundali-crimson-border)] bg-[var(--kundali-crimson-bg)] px-3.5 py-2.5 font-medium text-[var(--kundali-crimson)]"
            >
              {displayedErrors.length === 1 ? (
                <p>{displayedErrors[0]}</p>
              ) : (
                <ul className="list-disc space-y-1 pl-4">
                  {displayedErrors.map((msg) => (
                    <li key={msg}>{msg}</li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}

          <div>
            <label htmlFor="login-email" className="block font-semibold text-[var(--kundali-ink)]">
              {t.loginEmailLabel}
            </label>
            <input
              id="login-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              disabled={isFormBusy}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t.loginEmailPlaceholder}
              aria-invalid={validationFieldError === "emailInvalid" ? "true" : undefined}
              aria-describedby={displayedErrors.length > 0 ? "login-form-error" : undefined}
              className="mt-1.5 min-h-[44px] w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 text-sm text-[var(--kundali-ink)] disabled:cursor-not-allowed disabled:bg-[var(--kundali-strip)]"
            />
          </div>

          <div>
            <label
              htmlFor="login-password"
              className="block font-semibold text-[var(--kundali-ink)]"
            >
              {t.loginPasswordLabel}
            </label>
            <input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              disabled={isFormBusy}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t.loginPasswordPlaceholder}
              aria-invalid={validationFieldError === "passwordRequired" ? "true" : undefined}
              aria-describedby={displayedErrors.length > 0 ? "login-form-error" : undefined}
              className="mt-1.5 min-h-[44px] w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 text-sm text-[var(--kundali-ink)] disabled:cursor-not-allowed disabled:bg-[var(--kundali-strip)]"
            />
          </div>

          <button
            type="submit"
            disabled={isFormBusy}
            className="inline-flex min-h-[44px] w-full items-center justify-center rounded bg-[var(--kundali-navy)] px-4 py-2.5 text-sm font-semibold text-[var(--kundali-cream)] hover:bg-[var(--kundali-navy-hover)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? t.loginSubmitting : t.loginSubmit}
          </button>

          <p className="border-t border-[var(--kundali-border-subtle)] pt-4 text-center text-xs text-[var(--kundali-muted)]">
            {t.noAccountPrompt}{" "}
            <Link
              href="/register"
              className="font-semibold text-[var(--kundali-navy)] underline decoration-[var(--kundali-border)] underline-offset-2 hover:text-[var(--kundali-emerald)]"
            >
              {t.createAccountLink}
            </Link>
          </p>
        </form>
      ) : null}
    </AuthPanelLayout>
  );
}
