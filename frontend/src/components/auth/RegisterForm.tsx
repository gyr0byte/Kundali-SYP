"use client";

import Link from "next/link";
import React, { useEffect, useRef, useState } from "react";
import { useAuthSession } from "@/components/auth/AuthSessionProvider";
import { AuthPanelLayout } from "@/components/auth/AuthPanelLayout";
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  validateRegistrationInputs,
  type RegisterValidationErrorKey,
} from "@/lib/auth/navigation";
import {
  resolveLocalizedAuthErrors,
  type AuthLocale,
  type AuthMessages,
} from "@/lib/auth/ui-helpers";

export interface RegisterFormProps {
  messagesByLocale: Record<AuthLocale, AuthMessages>;
  initialLocale?: AuthLocale;
  onNavigate?: (href: string) => void;
}

export function RegisterForm({
  messagesByLocale,
  initialLocale = "en",
  onNavigate,
}: RegisterFormProps) {
  const session = useAuthSession();
  const [locale, setLocale] = useState<AuthLocale>(initialLocale);
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [confirmPassword, setConfirmPassword] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isRetryingSession, setIsRetryingSession] = useState<boolean>(false);
  const [registrationComplete, setRegistrationComplete] = useState<boolean>(false);
  const [errorMessages, setErrorMessages] = useState<string[]>([]);
  const [validationFieldError, setValidationFieldError] =
    useState<RegisterValidationErrorKey | null>(null);

  const submitLockRef = useRef<boolean>(false);
  const t = messagesByLocale[locale];

  useEffect(() => {
    if (session.status === "authenticated" && onNavigate) {
      onNavigate("/user");
    }
  }, [onNavigate, session.status]);

  async function handleRetrySession() {
    if (isRetryingSession || isSubmitting) {
      return;
    }
    setIsRetryingSession(true);
    try {
      const next = await session.retrySession();
      if (next.status === "authenticated") {
        onNavigate?.("/user");
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

    const validation = validateRegistrationInputs(email, password, confirmPassword);
    if (validation.errorKey) {
      setValidationFieldError(validation.errorKey);
      setErrorMessages([]);
      return;
    }

    setValidationFieldError(null);
    setErrorMessages([]);
    setRegistrationComplete(false);
    submitLockRef.current = true;
    setIsSubmitting(true);

    try {
      const result = await session.register(validation.email, password);
      if (result.ok) {
        setPassword("");
        setConfirmPassword("");
        setRegistrationComplete(true);
        onNavigate?.("/login?registered=1");
        return;
      }
      setErrorMessages(resolveLocalizedAuthErrors(result, t));
    } finally {
      submitLockRef.current = false;
      setIsSubmitting(false);
    }
  }

  function resolveClientValidationMessage(key: RegisterValidationErrorKey): string {
    switch (key) {
      case "emailInvalid":
        return t.validationEmailInvalid;
      case "passwordTooShort":
        return t.validationPasswordTooShort;
      case "passwordTooLong":
        return t.validationPasswordTooLong;
      case "passwordMismatch":
        return t.validationPasswordMismatch;
    }
  }

  const displayedErrors = validationFieldError
    ? [resolveClientValidationMessage(validationFieldError)]
    : errorMessages;

  const isChecking = session.status === "checking";
  const isUnavailable = session.status === "unavailable";
  const isFormBusy = isSubmitting || isRetryingSession;

  return (
    <AuthPanelLayout
      locale={locale}
      onLocaleChange={setLocale}
      messages={t}
      title={t.registerTitle}
      subtitle={t.registerSubtitle}
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
          <p className="mt-1 leading-relaxed text-[var(--kundali-ink)]">{t.unavailableBody}</p>
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

      {!isChecking && registrationComplete ? (
        <div
          role="status"
          className="mb-4 rounded border border-[var(--kundali-emerald-border)] bg-[var(--kundali-emerald-bg)] px-3.5 py-2.5 text-xs font-medium text-[var(--kundali-emerald)]"
        >
          {t.registerSuccessNotice}
        </div>
      ) : null}

      {!isChecking ? (
        <form onSubmit={handleSubmit} className="space-y-4 text-xs" noValidate>
          {displayedErrors.length > 0 ? (
            <div
              id="register-form-error"
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
            <label
              htmlFor="register-email"
              className="block font-semibold text-[var(--kundali-ink)]"
            >
              {t.registerEmailLabel}
            </label>
            <input
              id="register-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              disabled={isFormBusy}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t.registerEmailPlaceholder}
              aria-invalid={validationFieldError === "emailInvalid" ? "true" : undefined}
              aria-describedby={displayedErrors.length > 0 ? "register-form-error" : undefined}
              className="mt-1.5 min-h-[44px] w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 text-sm text-[var(--kundali-ink)] disabled:cursor-not-allowed disabled:bg-[var(--kundali-strip)]"
            />
          </div>

          <div>
            <label
              htmlFor="register-password"
              className="block font-semibold text-[var(--kundali-ink)]"
            >
              {t.registerPasswordLabel}
            </label>
            <input
              id="register-password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={PASSWORD_MIN_LENGTH}
              maxLength={PASSWORD_MAX_LENGTH}
              disabled={isFormBusy}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t.registerPasswordPlaceholder}
              aria-invalid={
                validationFieldError === "passwordTooShort" ||
                validationFieldError === "passwordTooLong"
                  ? "true"
                  : undefined
              }
              aria-describedby={
                displayedErrors.length > 0
                  ? "register-password-rules register-form-error"
                  : "register-password-rules"
              }
              className="mt-1.5 min-h-[44px] w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 text-sm text-[var(--kundali-ink)] disabled:cursor-not-allowed disabled:bg-[var(--kundali-strip)]"
            />
            <p
              id="register-password-rules"
              className="mt-1.5 text-[11px] leading-relaxed text-[var(--kundali-muted)]"
            >
              {t.passwordRulesSummary}
            </p>
          </div>

          <div>
            <label
              htmlFor="register-confirm-password"
              className="block font-semibold text-[var(--kundali-ink)]"
            >
              {t.registerConfirmPasswordLabel}
            </label>
            <input
              id="register-confirm-password"
              name="confirmPassword"
              type="password"
              autoComplete="new-password"
              required
              minLength={PASSWORD_MIN_LENGTH}
              maxLength={PASSWORD_MAX_LENGTH}
              disabled={isFormBusy}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder={t.registerConfirmPasswordPlaceholder}
              aria-invalid={validationFieldError === "passwordMismatch" ? "true" : undefined}
              aria-describedby={displayedErrors.length > 0 ? "register-form-error" : undefined}
              className="mt-1.5 min-h-[44px] w-full rounded border border-[var(--kundali-border)] bg-[var(--kundali-surface)] px-3 py-2 text-sm text-[var(--kundali-ink)] disabled:cursor-not-allowed disabled:bg-[var(--kundali-strip)]"
            />
          </div>

          <button
            type="submit"
            disabled={isFormBusy}
            className="inline-flex min-h-[44px] w-full items-center justify-center rounded bg-[var(--kundali-navy)] px-4 py-2.5 text-sm font-semibold text-[var(--kundali-cream)] hover:bg-[var(--kundali-navy-hover)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? t.registerSubmitting : t.registerSubmit}
          </button>

          <p className="border-t border-[var(--kundali-border-subtle)] pt-4 text-center text-xs text-[var(--kundali-muted)]">
            {t.alreadyHaveAccountPrompt}{" "}
            <Link
              href="/login"
              className="font-semibold text-[var(--kundali-navy)] underline decoration-[var(--kundali-border)] underline-offset-2 hover:text-[var(--kundali-emerald)]"
            >
              {t.signInLink}
            </Link>
          </p>
        </form>
      ) : null}
    </AuthPanelLayout>
  );
}
