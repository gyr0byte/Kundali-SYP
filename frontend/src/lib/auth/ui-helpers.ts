import type { AuthMutationResult, LogoutAllResult, LogoutResult } from "./session-client.ts";

export type AuthLocale = "en" | "ne";

export interface AuthMessages {
  brandName: string;
  brandNative: string;
  brandSubtitle: string;
  localeLabel: string;
  skipToForm: string;
  backToWorkspace: string;
  observatoryBadge: string;
  checkingSessionTitle: string;
  checkingSessionBody: string;
  unavailableTitle: string;
  unavailableBody: string;
  retrySessionButton: string;
  retryingSessionButton: string;
  registeredBanner: string;
  loginTitle: string;
  loginSubtitle: string;
  loginEmailLabel: string;
  loginEmailPlaceholder: string;
  loginPasswordLabel: string;
  loginPasswordPlaceholder: string;
  loginSubmit: string;
  loginSubmitting: string;
  noAccountPrompt: string;
  createAccountLink: string;
  registerTitle: string;
  registerSubtitle: string;
  registerEmailLabel: string;
  registerEmailPlaceholder: string;
  registerPasswordLabel: string;
  registerPasswordPlaceholder: string;
  registerConfirmPasswordLabel: string;
  registerConfirmPasswordPlaceholder: string;
  passwordRulesSummary: string;
  registerSubmit: string;
  registerSubmitting: string;
  alreadyHaveAccountPrompt: string;
  signInLink: string;
  validationEmailInvalid: string;
  validationPasswordRequired: string;
  validationPasswordTooShort: string;
  validationPasswordTooLong: string;
  validationPasswordMismatch: string;
  errorInvalidCredentials: string;
  errorDuplicateEmail: string;
  errorRateLimitedNoDelay: string;
  errorRateLimitedWithSeconds: string;
  errorRateLimitedWithHeader: string;
  errorBackendUnavailable: string;
  errorSessionRecovery: string;
  errorGeneric: string;
  registerSuccessNotice: string;
}

export interface LogoutOutcomeBanner {
  tone: "emerald" | "amber" | "crimson";
  message: string;
}

export interface LogoutOutcomeMessages {
  logoutOutcomeConfirmed: string;
  logoutOutcomeUnconfirmed: string;
  logoutOutcomeNetworkError: string;
  logoutAllConfirmedNotice: string;
  logoutAllFailedNotice: string;
}

/**
 * Translates sanitized session mutation errors cleanly without inventing delays
 * or leaking unvalidated fields.
 */
export function resolveLocalizedAuthErrors(
  result: AuthMutationResult,
  t: AuthMessages
): string[] {
  if (result.code === "INVALID_CREDENTIALS" || result.status === 401) {
    return [t.errorInvalidCredentials];
  }

  if (result.code === "RATE_LIMITED" || result.status === 429) {
    if (typeof result.retryAfterSeconds === "number" && Number.isFinite(result.retryAfterSeconds)) {
      return [t.errorRateLimitedWithSeconds.replace("{seconds}", String(result.retryAfterSeconds))];
    }
    if (typeof result.retryAfter === "string" && result.retryAfter.trim()) {
      return [t.errorRateLimitedWithHeader.replace("{retryAfter}", result.retryAfter.trim())];
    }
    return [t.errorRateLimitedNoDelay];
  }

  if (result.code === "SESSION_RECOVERY_UNAVAILABLE") {
    return [t.errorSessionRecovery];
  }

  if (result.code === "VALIDATION_ERROR" || result.status === 422) {
    if (result.validationMessages && result.validationMessages.length > 0) {
      return [...result.validationMessages];
    }
    return [result.message?.trim() || t.errorGeneric];
  }

  if (result.code === "REGISTRATION_REJECTED" || result.status === 400) {
    const rawMsg = result.message ?? "";
    if (/already registered/i.test(rawMsg)) {
      return [t.errorDuplicateEmail];
    }
    return [rawMsg.trim() || t.errorGeneric];
  }

  if (result.code === "BACKEND_UNAVAILABLE" || (result.status !== null && result.status >= 500)) {
    return [t.errorBackendUnavailable];
  }

  return [result.message?.trim() || t.errorGeneric];
}

export function classifyLogoutOutcome(
  result: LogoutResult,
  t: LogoutOutcomeMessages
): LogoutOutcomeBanner {
  if (result.localCookieCleared && result.backendLogoutRequestCompleted) {
    return {
      tone: "emerald",
      message: t.logoutOutcomeConfirmed,
    };
  }
  if (result.localCookieCleared) {
    return {
      tone: "amber",
      message: t.logoutOutcomeUnconfirmed,
    };
  }
  return {
    tone: "crimson",
    message: t.logoutOutcomeNetworkError,
  };
}

export function classifyLogoutAllOutcome(
  result: LogoutAllResult,
  t: LogoutOutcomeMessages
): LogoutOutcomeBanner {
  if (result.ok) {
    return {
      tone: "emerald",
      message: t.logoutAllConfirmedNotice,
    };
  }
  const detail = result.message?.trim();
  return {
    tone: "crimson",
    message: detail ? `${t.logoutAllFailedNotice} (${detail})` : t.logoutAllFailedNotice,
  };
}
