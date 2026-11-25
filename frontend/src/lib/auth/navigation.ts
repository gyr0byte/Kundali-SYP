const DEFAULT_POST_LOGIN_PATH = "/user";

const PERMITTED_POST_LOGIN_EXACT_PATHS = new Set<string>(["/", "/user", "/admin", "/astrologer"]);

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const PASSWORD_MIN_LENGTH = 10;
export const PASSWORD_MAX_LENGTH = 128;

/**
 * Validates and normalizes post-login redirect destinations strictly to permitted
 * internal application paths, rejecting external, protocol-relative, backslash,
 * control-character, or encoded-bypass inputs.
 */
export function resolveSafePostLoginRedirect(rawRedirect?: string | null): string {
  if (typeof rawRedirect !== "string") {
    return DEFAULT_POST_LOGIN_PATH;
  }
  const trimmed = rawRedirect.trim();
  if (!trimmed) {
    return DEFAULT_POST_LOGIN_PATH;
  }

  // Reject ASCII control characters, backslashes, or non-leading-slash / protocol-relative paths early.
  if (
    /[\u0000-\u001f\u007f]/.test(trimmed) ||
    trimmed.includes("\\") ||
    !trimmed.startsWith("/") ||
    trimmed.startsWith("//")
  ) {
    return DEFAULT_POST_LOGIN_PATH;
  }

  // Reject malformed or obfuscated encodings (e.g. %5c backslash, %2f%2f, scheme colons, control chars).
  let current = trimmed;
  for (let pass = 0; pass < 2; pass += 1) {
    let decoded: string;
    try {
      decoded = decodeURIComponent(current);
    } catch {
      return DEFAULT_POST_LOGIN_PATH;
    }
    if (/[\u0000-\u001f\u007f]/.test(decoded) || decoded.includes("\\") || decoded.startsWith("//")) {
      return DEFAULT_POST_LOGIN_PATH;
    }
    if (decoded === current) {
      break;
    }
    current = decoded;
  }

  // Disallow literal %2f / %5c tricks in the raw pathname segment before query/hash.
  const rawPathSegment = trimmed.split(/[?#]/, 1)[0] ?? "";
  if (/%2f|%5c/i.test(rawPathSegment) || rawPathSegment.includes(":")) {
    return DEFAULT_POST_LOGIN_PATH;
  }

  let parsed: URL;
  try {
    parsed = new URL(trimmed, "https://kundali.local");
  } catch {
    return DEFAULT_POST_LOGIN_PATH;
  }

  if (parsed.origin !== "https://kundali.local" || parsed.username || parsed.password) {
    return DEFAULT_POST_LOGIN_PATH;
  }

  const normalizedPath = parsed.pathname;
  if (!PERMITTED_POST_LOGIN_EXACT_PATHS.has(normalizedPath)) {
    return DEFAULT_POST_LOGIN_PATH;
  }

  return `${normalizedPath}${parsed.search}${parsed.hash}`;
}

export type LoginValidationErrorKey = "emailInvalid" | "passwordRequired";
export type RegisterValidationErrorKey =
  | "emailInvalid"
  | "passwordTooShort"
  | "passwordTooLong"
  | "passwordMismatch";

export function validateLoginInputs(email: string, password: string): {
  email: string;
  errorKey: LoginValidationErrorKey | null;
} {
  const normalizedEmail = email.trim();
  if (!EMAIL_PATTERN.test(normalizedEmail)) {
    return { email: normalizedEmail, errorKey: "emailInvalid" };
  }
  if (password.length === 0) {
    return { email: normalizedEmail, errorKey: "passwordRequired" };
  }
  return { email: normalizedEmail, errorKey: null };
}

export function validateRegistrationInputs(
  email: string,
  password: string,
  confirmPassword: string
): {
  email: string;
  errorKey: RegisterValidationErrorKey | null;
} {
  const normalizedEmail = email.trim();
  if (!EMAIL_PATTERN.test(normalizedEmail)) {
    return { email: normalizedEmail, errorKey: "emailInvalid" };
  }
  if (password.length < PASSWORD_MIN_LENGTH) {
    return { email: normalizedEmail, errorKey: "passwordTooShort" };
  }
  if (password.length > PASSWORD_MAX_LENGTH) {
    return { email: normalizedEmail, errorKey: "passwordTooLong" };
  }
  if (password !== confirmPassword) {
    return { email: normalizedEmail, errorKey: "passwordMismatch" };
  }
  return { email: normalizedEmail, errorKey: null };
}
