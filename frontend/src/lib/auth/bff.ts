/**
 * Server-only Next.js BFF helpers for FastAPI authentication.
 *
 * Security invariants:
 * - Refresh tokens live exclusively in an HttpOnly cookie (`kundali_refresh_token`)
 *   scoped to `/api/auth` with `SameSite=Lax`, `Max-Age=7d`, and `Secure` in prod.
 * - Refresh tokens are NEVER returned in client-facing JSON responses or logged.
 * - Backend URL comes strictly from server-side `KUNDALI_API_BASE_URL`.
 * - State-changing BFF routes require exact `KUNDALI_FRONTEND_ORIGIN` match and
 *   custom header `X-Kundali-CSRF: 1` (never trusting `Host` or `X-Forwarded-*`).
 * - Known concurrency limitation: FastAPI `refresh_tokens()` revokes an entire
 *   token family upon reuse of any already-revoked token. BFF handlers execute
 *   one upstream refresh per request without fanning out; single-flight /
 *   cross-tab client coordination belongs to Commit 2, and backend locking /
 *   concurrency hardening belongs to a separate backend evaluation before prod.
 */

export const REFRESH_COOKIE_NAME = "kundali_refresh_token";
export const REFRESH_COOKIE_PATH = "/api/auth";
export const REFRESH_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60;
export const CSRF_HEADER_NAME = "x-kundali-csrf";
export const CSRF_HEADER_VALUE = "1";

const DEV_FALLBACK_API_BASE_URL = "http://127.0.0.1:8000/api/v1";
const DEV_FALLBACK_FRONTEND_ORIGIN = "http://localhost:3000";

export interface BffUser {
  id: string;
  email: string;
  role: string;
  language: string;
  is_active: boolean;
  created_at: string;
}

export interface BffConfig {
  apiBaseUrl?: string;
  frontendOrigin?: string;
  isProduction?: boolean;
  fetchImpl?: typeof fetch;
}

interface ResolvedBffRuntime {
  apiBaseUrl: string;
  frontendOrigin: string;
  isProduction: boolean;
  fetchImpl: typeof fetch;
}

class BffConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BffConfigError";
  }
}

function assertServerSide(): void {
  if (typeof window !== "undefined") {
    throw new Error("Kundali BFF authentication helpers must only execute on the server.");
  }
}

export function normalizeBackendApiBaseUrl(rawUrl: string | undefined, isProduction: boolean): string {
  const trimmed = typeof rawUrl === "string" ? rawUrl.trim() : "";
  const candidate = trimmed || (isProduction ? "" : DEV_FALLBACK_API_BASE_URL);
  if (!candidate) {
    throw new BffConfigError("KUNDALI_API_BASE_URL must be explicitly configured in production.");
  }

  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new BffConfigError("KUNDALI_API_BASE_URL must be a valid URL.");
  }

  if (isProduction && parsed.protocol !== "https:") {
    throw new BffConfigError("KUNDALI_API_BASE_URL must use HTTPS in production.");
  }
  if (!isProduction && parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new BffConfigError("KUNDALI_API_BASE_URL must use HTTP or HTTPS.");
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new BffConfigError("KUNDALI_API_BASE_URL must not contain credentials, query, or hash.");
  }

  return parsed.toString().replace(/\/+$/, "");
}

export function normalizeTrustedFrontendOrigin(
  rawOrigin: string | undefined,
  isProduction: boolean
): string {
  const trimmed = typeof rawOrigin === "string" ? rawOrigin.trim() : "";
  const candidate = trimmed || (isProduction ? "" : DEV_FALLBACK_FRONTEND_ORIGIN);
  if (!candidate) {
    throw new BffConfigError(
      "KUNDALI_FRONTEND_ORIGIN must be explicitly configured in production."
    );
  }

  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new BffConfigError("KUNDALI_FRONTEND_ORIGIN must be a valid origin URL.");
  }

  if (isProduction && parsed.protocol !== "https:") {
    throw new BffConfigError("KUNDALI_FRONTEND_ORIGIN must use HTTPS in production.");
  }
  if (!isProduction && parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new BffConfigError("KUNDALI_FRONTEND_ORIGIN must use HTTP or HTTPS.");
  }
  if (
    parsed.username ||
    parsed.password ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash
  ) {
    throw new BffConfigError(
      "KUNDALI_FRONTEND_ORIGIN must be an origin only without path, query, or credentials."
    );
  }

  return parsed.origin;
}

function resolveRuntime(config: BffConfig = {}): ResolvedBffRuntime {
  assertServerSide();
  const isProduction = config.isProduction ?? process.env.NODE_ENV === "production";
  const apiBaseUrl = normalizeBackendApiBaseUrl(
    config.apiBaseUrl ?? process.env.KUNDALI_API_BASE_URL,
    isProduction
  );
  const frontendOrigin = normalizeTrustedFrontendOrigin(
    config.frontendOrigin ?? process.env.KUNDALI_FRONTEND_ORIGIN,
    isProduction
  );
  const fetchImpl = config.fetchImpl ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    throw new BffConfigError("Server fetch implementation unavailable.");
  }
  return { apiBaseUrl, frontendOrigin, isProduction, fetchImpl };
}

export function joinBackendUrl(baseUrl: string, endpoint: string): string {
  const cleanBase = baseUrl.replace(/\/+$/, "");
  const cleanPath = endpoint.replace(/^\/+/, "");
  return `${cleanBase}/${cleanPath}`;
}

export function buildSetRefreshCookieHeader(
  refreshToken: string,
  options: { isProduction: boolean }
): string {
  const parts = [
    `${REFRESH_COOKIE_NAME}=${encodeURIComponent(refreshToken)}`,
    `Path=${REFRESH_COOKIE_PATH}`,
    `Max-Age=${REFRESH_COOKIE_MAX_AGE_SECONDS}`,
    "HttpOnly",
    "SameSite=Lax",
  ];
  if (options.isProduction) {
    parts.push("Secure");
  }
  return parts.join("; ");
}

export function buildClearRefreshCookieHeader(options: { isProduction: boolean }): string {
  const parts = [
    `${REFRESH_COOKIE_NAME}=`,
    `Path=${REFRESH_COOKIE_PATH}`,
    "Max-Age=0",
    "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
    "HttpOnly",
    "SameSite=Lax",
  ];
  if (options.isProduction) {
    parts.push("Secure");
  }
  return parts.join("; ");
}

export function readRefreshCookieFromRequest(request: Request): string | null {
  const cookieHeader = request.headers.get("cookie");
  if (!cookieHeader) {
    return null;
  }
  const pairs = cookieHeader.split(";");
  for (const rawPair of pairs) {
    const eqIndex = rawPair.indexOf("=");
    if (eqIndex <= 0) {
      continue;
    }
    const name = rawPair.slice(0, eqIndex).trim();
    if (name !== REFRESH_COOKIE_NAME) {
      continue;
    }
    const rawVal = rawPair.slice(eqIndex + 1).trim();
    if (!rawVal) {
      return null;
    }
    try {
      const decoded = decodeURIComponent(rawVal).trim();
      return decoded || null;
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * Extract unverified `exp` claim (epoch ms) strictly as a client scheduling hint.
 * Never use unverified claims for authorization decisions.
 */
export function extractAccessTokenExpiresAtMs(accessToken: string): number | null {
  const parts = accessToken.split(".");
  if (parts.length !== 3 || !parts[1]) {
    return null;
  }
  try {
    const jsonText = Buffer.from(parts[1], "base64url").toString("utf8");
    const parsed = JSON.parse(jsonText) as { exp?: unknown };
    if (typeof parsed.exp === "number" && Number.isFinite(parsed.exp) && parsed.exp > 0) {
      return Math.round(parsed.exp * 1000);
    }
    return null;
  } catch {
    return null;
  }
}

export function bffJsonResponse(
  payload: unknown,
  options: {
    status?: number;
    setCookieHeader?: string | null;
    retryAfter?: string | null;
  } = {}
): Response {
  const headers = new Headers({
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store, private",
    Pragma: "no-cache",
    Vary: "Cookie",
  });
  if (options.setCookieHeader) {
    headers.append("Set-Cookie", options.setCookieHeader);
  }
  if (options.retryAfter) {
    headers.set("Retry-After", options.retryAfter);
  }
  return new Response(JSON.stringify(payload), {
    status: options.status ?? 200,
    headers,
  });
}

function errorJsonResponse(params: {
  status: number;
  code: string;
  message: string;
  validationMessages?: string[];
  setCookieHeader?: string | null;
  retryAfter?: string | null;
  extra?: Record<string, unknown>;
}): Response {
  return bffJsonResponse(
    {
      ...(params.extra ?? {}),
      error: {
        code: params.code,
        message: params.message,
        ...(params.validationMessages?.length
          ? { validation_messages: params.validationMessages }
          : {}),
      },
    },
    {
      status: params.status,
      setCookieHeader: params.setCookieHeader,
      retryAfter: params.retryAfter,
    }
  );
}

function isJsonMimeType(contentType: string | null): boolean {
  if (!contentType) {
    return false;
  }
  const mediaType = contentType.split(";")[0]?.trim().toLowerCase() ?? "";
  return mediaType === "application/json";
}

function validateCsrfAndOrigin(
  request: Request,
  trustedOrigin: string,
  options: { requireJsonContentType: boolean }
): Response | null {
  const originHeader = request.headers.get("origin");
  if (!originHeader || originHeader.trim() !== trustedOrigin) {
    return errorJsonResponse({
      status: 403,
      code: "CSRF_ORIGIN_REJECTED",
      message: "Request origin is missing or untrusted.",
    });
  }

  const csrfHeader = request.headers.get(CSRF_HEADER_NAME);
  if (csrfHeader !== CSRF_HEADER_VALUE) {
    return errorJsonResponse({
      status: 403,
      code: "CSRF_HEADER_REQUIRED",
      message: "Required CSRF verification header is missing or invalid.",
    });
  }

  const contentType = request.headers.get("content-type");
  if (options.requireJsonContentType) {
    if (!isJsonMimeType(contentType)) {
      return errorJsonResponse({
        status: 415,
        code: "UNSUPPORTED_MEDIA_TYPE",
        message: "Content-Type must be application/json.",
      });
    }
  } else if (contentType && !isJsonMimeType(contentType)) {
    return errorJsonResponse({
      status: 415,
      code: "UNSUPPORTED_MEDIA_TYPE",
      message: "Content-Type must be application/json when provided.",
    });
  }

  return null;
}

async function readCredentialsBody(
  request: Request
): Promise<{ email: string; password: string } | Response> {
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return errorJsonResponse({
      status: 400,
      code: "INVALID_JSON",
      message: "Request body must be valid JSON.",
    });
  }

  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return errorJsonResponse({
      status: 422,
      code: "VALIDATION_ERROR",
      message: "Email and password are required.",
    });
  }

  const email = (raw as { email?: unknown }).email;
  const password = (raw as { password?: unknown }).password;
  if (
    typeof email !== "string" ||
    !email.trim() ||
    typeof password !== "string" ||
    !password
  ) {
    return errorJsonResponse({
      status: 422,
      code: "VALIDATION_ERROR",
      message: "Valid email and password strings are required.",
    });
  }

  return { email: email.trim(), password };
}

function sanitizeValidationMessages(body: unknown): string[] {
  if (!body || typeof body !== "object") {
    return [];
  }
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) {
    return [detail.trim()];
  }
  if (!Array.isArray(detail)) {
    return [];
  }
  const messages: string[] = [];
  for (const item of detail) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const rawMsg = (item as { msg?: unknown }).msg;
    if (typeof rawMsg !== "string" || !rawMsg.trim()) {
      continue;
    }
    const loc = (item as { loc?: unknown }).loc;
    const fieldName =
      Array.isArray(loc) && loc.length > 0 ? String(loc[loc.length - 1]) : "";
    const cleanedMsg = rawMsg.replace(/^Value error,\s*/i, "").trim();
    messages.push(
      fieldName && fieldName !== "body" ? `${fieldName}: ${cleanedMsg}` : cleanedMsg
    );
  }
  return Array.from(new Set(messages));
}

function sanitizeBackendDetailString(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") {
    return fallback;
  }
  const detail = (body as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.trim() ? detail.trim() : fallback;
}

function sanitizeBffUser(body: unknown): BffUser | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }
  const candidate = body as Record<string, unknown>;
  if (
    typeof candidate.id !== "string" ||
    typeof candidate.email !== "string" ||
    typeof candidate.role !== "string" ||
    typeof candidate.language !== "string" ||
    typeof candidate.is_active !== "boolean" ||
    typeof candidate.created_at !== "string"
  ) {
    return null;
  }
  return {
    id: candidate.id,
    email: candidate.email,
    role: candidate.role,
    language: candidate.language,
    is_active: candidate.is_active,
    created_at: candidate.created_at,
  };
}

function extractTokenPair(
  body: unknown
): { accessToken: string; refreshToken: string; tokenType: string } | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }
  const raw = body as Record<string, unknown>;
  if (
    typeof raw.access_token !== "string" ||
    !raw.access_token.trim() ||
    typeof raw.refresh_token !== "string" ||
    !raw.refresh_token.trim()
  ) {
    return null;
  }
  const tokenType =
    typeof raw.token_type === "string" && raw.token_type.trim() ? raw.token_type.trim() : "bearer";
  return {
    accessToken: raw.access_token.trim(),
    refreshToken: raw.refresh_token.trim(),
    tokenType,
  };
}

async function safeParseJson(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    return null;
  }
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function fetchBackendJson(
  runtime: ResolvedBffRuntime,
  endpoint: string,
  init: {
    method: "GET" | "POST";
    body?: unknown;
    bearerToken?: string;
  }
): Promise<{ response: Response; body: unknown } | null> {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (init.bearerToken) {
    headers.Authorization = `Bearer ${init.bearerToken}`;
  }
  let serializedBody: string | undefined;
  if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
    serializedBody = JSON.stringify(init.body);
  }

  try {
    const response = await runtime.fetchImpl(joinBackendUrl(runtime.apiBaseUrl, endpoint), {
      method: init.method,
      headers,
      body: serializedBody,
      cache: "no-store",
    });
    const body = await safeParseJson(response);
    return { response, body };
  } catch {
    return null;
  }
}

async function fetchCurrentUser(
  runtime: ResolvedBffRuntime,
  accessToken: string
): Promise<{ status: number; user: BffUser | null }> {
  const result = await fetchBackendJson(runtime, "/me", {
    method: "GET",
    bearerToken: accessToken,
  });
  if (!result) {
    return { status: 503, user: null };
  }
  if (!result.response.ok) {
    return { status: result.response.status, user: null };
  }
  const user = sanitizeBffUser(result.body);
  if (!user) {
    return { status: 502, user: null };
  }
  return { status: 200, user };
}

function handleSetupOrSecurityPrelude(
  request: Request,
  config: BffConfig,
  options: { requireJsonContentType: boolean }
): { runtime: ResolvedBffRuntime; errorResponse: null } | { runtime: null; errorResponse: Response } {
  let runtime: ResolvedBffRuntime;
  try {
    runtime = resolveRuntime(config);
  } catch {
    return {
      runtime: null,
      errorResponse: errorJsonResponse({
        status: 500,
        code: "BFF_MISCONFIGURED",
        message: "Authentication service configuration is invalid.",
      }),
    };
  }

  const csrfFailure = validateCsrfAndOrigin(request, runtime.frontendOrigin, options);
  if (csrfFailure) {
    return { runtime: null, errorResponse: csrfFailure };
  }

  return { runtime, errorResponse: null };
}

export async function handleRegister(request: Request, config: BffConfig = {}): Promise<Response> {
  const prelude = handleSetupOrSecurityPrelude(request, config, {
    requireJsonContentType: true,
  });
  if (prelude.errorResponse) {
    return prelude.errorResponse;
  }
  const { runtime } = prelude;

  const creds = await readCredentialsBody(request);
  if (creds instanceof Response) {
    return creds;
  }

  const upstream = await fetchBackendJson(runtime, "/auth/register", {
    method: "POST",
    body: { email: creds.email, password: creds.password },
  });
  if (!upstream) {
    return errorJsonResponse({
      status: 503,
      code: "BACKEND_UNAVAILABLE",
      message: "Authentication service is temporarily unavailable.",
    });
  }

  const { response, body } = upstream;
  if (response.status === 201) {
    const user = sanitizeBffUser(body);
    if (!user) {
      return errorJsonResponse({
        status: 502,
        code: "INVALID_BACKEND_RESPONSE",
        message: "Received an invalid response from authentication service.",
      });
    }
    return bffJsonResponse(user, { status: 201 });
  }

  if (response.status === 400) {
    return errorJsonResponse({
      status: 400,
      code: "REGISTRATION_REJECTED",
      message: sanitizeBackendDetailString(body, "Registration failed."),
    });
  }

  if (response.status === 422) {
    const validationMessages = sanitizeValidationMessages(body);
    return errorJsonResponse({
      status: 422,
      code: "VALIDATION_ERROR",
      message: validationMessages[0] ?? "Registration details failed validation.",
      validationMessages,
    });
  }

  return errorJsonResponse({
    status: response.status >= 500 ? 502 : response.status,
    code: "BACKEND_UNAVAILABLE",
    message: "Authentication service is temporarily unavailable.",
  });
}

export async function handleLogin(request: Request, config: BffConfig = {}): Promise<Response> {
  const prelude = handleSetupOrSecurityPrelude(request, config, {
    requireJsonContentType: true,
  });
  if (prelude.errorResponse) {
    return prelude.errorResponse;
  }
  const { runtime } = prelude;

  const creds = await readCredentialsBody(request);
  if (creds instanceof Response) {
    return creds;
  }

  const upstream = await fetchBackendJson(runtime, "/auth/login", {
    method: "POST",
    body: { email: creds.email, password: creds.password },
  });
  if (!upstream) {
    return errorJsonResponse({
      status: 503,
      code: "BACKEND_UNAVAILABLE",
      message: "Authentication service is temporarily unavailable.",
    });
  }

  const { response, body } = upstream;
  if (response.status === 429) {
    return errorJsonResponse({
      status: 429,
      code: "RATE_LIMITED",
      message: sanitizeBackendDetailString(
        body,
        "Too many failed attempts. Please try again later."
      ),
      retryAfter: response.headers.get("retry-after"),
    });
  }

  if (response.status === 401) {
    return errorJsonResponse({
      status: 401,
      code: "INVALID_CREDENTIALS",
      message: "Invalid email or password.",
    });
  }

  if (response.status === 422) {
    const validationMessages = sanitizeValidationMessages(body);
    return errorJsonResponse({
      status: 422,
      code: "VALIDATION_ERROR",
      message: validationMessages[0] ?? "Login details failed validation.",
      validationMessages,
    });
  }

  if (!response.ok) {
    return errorJsonResponse({
      status: response.status >= 500 ? 502 : response.status,
      code: "BACKEND_UNAVAILABLE",
      message: "Authentication service is temporarily unavailable.",
    });
  }

  const pair = extractTokenPair(body);
  if (!pair) {
    return errorJsonResponse({
      status: 502,
      code: "INVALID_BACKEND_RESPONSE",
      message: "Received an invalid token response from authentication service.",
    });
  }

  const setCookieHeader = buildSetRefreshCookieHeader(pair.refreshToken, {
    isProduction: runtime.isProduction,
  });

  const meResult = await fetchCurrentUser(runtime, pair.accessToken);
  if (meResult.status !== 200 || !meResult.user) {
    if (meResult.status === 401) {
      return errorJsonResponse({
        status: 401,
        code: "SESSION_REJECTED",
        message: "Signed in token was rejected by account verification.",
        setCookieHeader: buildClearRefreshCookieHeader({ isProduction: runtime.isProduction }),
      });
    }
    // Preserve valid refresh cookie when /me fails temporarily after login succeeded.
    return errorJsonResponse({
      status: 503,
      code: "PROFILE_FETCH_FAILED",
      message:
        "Signed in, but user details could not be loaded temporarily. Retry session refresh.",
      setCookieHeader,
      extra: { session_established: true },
    });
  }

  return bffJsonResponse(
    {
      authenticated: true,
      access_token: pair.accessToken,
      token_type: pair.tokenType,
      expires_at: extractAccessTokenExpiresAtMs(pair.accessToken),
      user: meResult.user,
    },
    { status: 200, setCookieHeader }
  );
}

export async function handleRefresh(request: Request, config: BffConfig = {}): Promise<Response> {
  const prelude = handleSetupOrSecurityPrelude(request, config, {
    requireJsonContentType: false,
  });
  if (prelude.errorResponse) {
    return prelude.errorResponse;
  }
  const { runtime } = prelude;

  const currentRefreshToken = readRefreshCookieFromRequest(request);
  if (!currentRefreshToken) {
    return bffJsonResponse(
      {
        authenticated: false,
        access_token: null,
        expires_at: null,
        user: null,
      },
      { status: 200 }
    );
  }

  const upstream = await fetchBackendJson(runtime, "/auth/refresh", {
    method: "POST",
    body: { refresh_token: currentRefreshToken },
  });
  if (!upstream) {
    // Temporary backend unavailability before rotation: preserve existing cookie.
    return errorJsonResponse({
      status: 503,
      code: "BACKEND_UNAVAILABLE",
      message: "Authentication service is temporarily unavailable.",
    });
  }

  const { response, body } = upstream;
  if (response.status === 401 || response.status === 400 || response.status === 422) {
    // Token invalid, expired, revoked, or reused: clear cookie cleanly.
    return errorJsonResponse({
      status: 401,
      code: "SESSION_EXPIRED",
      message: "Invalid or expired refresh session.",
      setCookieHeader: buildClearRefreshCookieHeader({ isProduction: runtime.isProduction }),
      extra: { authenticated: false, access_token: null, user: null },
    });
  }

  if (!response.ok) {
    // 5xx before confirmed rotation: preserve existing cookie rather than clearing.
    return errorJsonResponse({
      status: 503,
      code: "BACKEND_UNAVAILABLE",
      message: "Authentication service is temporarily unavailable.",
    });
  }

  const pair = extractTokenPair(body);
  if (!pair) {
    return errorJsonResponse({
      status: 502,
      code: "INVALID_BACKEND_RESPONSE",
      message: "Received an invalid token response from authentication service.",
    });
  }

  // CRITICAL: FastAPI has already revoked the old token and issued this replacement.
  // Always persist this replacement cookie on outgoing responses even if /me fails next.
  const replacementCookieHeader = buildSetRefreshCookieHeader(pair.refreshToken, {
    isProduction: runtime.isProduction,
  });

  const meResult = await fetchCurrentUser(runtime, pair.accessToken);
  if (meResult.status !== 200 || !meResult.user) {
    if (meResult.status === 401) {
      return errorJsonResponse({
        status: 401,
        code: "SESSION_EXPIRED",
        message: "Account is no longer active.",
        setCookieHeader: buildClearRefreshCookieHeader({ isProduction: runtime.isProduction }),
        extra: { authenticated: false, access_token: null, user: null },
      });
    }
    return errorJsonResponse({
      status: 503,
      code: "PROFILE_FETCH_FAILED",
      message:
        "Session refreshed, but account profile is temporarily unavailable. Retry refresh.",
      setCookieHeader: replacementCookieHeader,
      extra: { rotated: true },
    });
  }

  return bffJsonResponse(
    {
      authenticated: true,
      access_token: pair.accessToken,
      token_type: pair.tokenType,
      expires_at: extractAccessTokenExpiresAtMs(pair.accessToken),
      user: meResult.user,
    },
    { status: 200, setCookieHeader: replacementCookieHeader }
  );
}

export async function handleLogout(request: Request, config: BffConfig = {}): Promise<Response> {
  const prelude = handleSetupOrSecurityPrelude(request, config, {
    requireJsonContentType: false,
  });
  if (prelude.errorResponse) {
    return prelude.errorResponse;
  }
  const { runtime } = prelude;

  const clearCookieHeader = buildClearRefreshCookieHeader({
    isProduction: runtime.isProduction,
  });
  const currentRefreshToken = readRefreshCookieFromRequest(request);
  if (!currentRefreshToken) {
    return bffJsonResponse(
      {
        local_cookie_cleared: true,
        backend_revoked: false,
        reason: "missing_cookie",
      },
      { status: 200, setCookieHeader: clearCookieHeader }
    );
  }

  const upstream = await fetchBackendJson(runtime, "/auth/logout", {
    method: "POST",
    body: { refresh_token: currentRefreshToken },
  });
  if (!upstream || !upstream.response.ok) {
    return bffJsonResponse(
      {
        local_cookie_cleared: true,
        backend_revoked: false,
        reason: "backend_unconfirmed",
      },
      { status: 200, setCookieHeader: clearCookieHeader }
    );
  }

  return bffJsonResponse(
    {
      local_cookie_cleared: true,
      backend_revoked: true,
    },
    { status: 200, setCookieHeader: clearCookieHeader }
  );
}

export async function handleLogoutAll(request: Request, config: BffConfig = {}): Promise<Response> {
  const prelude = handleSetupOrSecurityPrelude(request, config, {
    requireJsonContentType: false,
  });
  if (prelude.errorResponse) {
    return prelude.errorResponse;
  }
  const { runtime } = prelude;

  const authHeader = request.headers.get("authorization");
  const match = authHeader ? /^Bearer\s+(\S+)$/i.exec(authHeader.trim()) : null;
  const bearerToken = match?.[1]?.trim() ?? "";
  if (!bearerToken) {
    return errorJsonResponse({
      status: 401,
      code: "AUTH_REQUIRED",
      message: "Valid Bearer access token is required for logout-all.",
      extra: { local_cookie_cleared: false, backend_revoked: false },
    });
  }

  const upstream = await fetchBackendJson(runtime, "/auth/logout-all", {
    method: "POST",
    bearerToken,
  });
  if (!upstream) {
    return errorJsonResponse({
      status: 503,
      code: "BACKEND_UNAVAILABLE",
      message: "Authentication service is temporarily unavailable.",
      extra: { local_cookie_cleared: false, backend_revoked: false },
    });
  }

  const { response } = upstream;
  if (response.status === 401 || response.status === 403) {
    // Keep refresh cookie intact on 401 so Commit 2 can refresh then retry logout-all.
    return errorJsonResponse({
      status: response.status,
      code: response.status === 401 ? "UNAUTHORIZED" : "FORBIDDEN",
      message: "Access token rejected by backend during logout-all.",
      extra: { local_cookie_cleared: false, backend_revoked: false },
    });
  }

  if (!response.ok) {
    return errorJsonResponse({
      status: response.status >= 500 ? 502 : response.status,
      code: "BACKEND_UNAVAILABLE",
      message: "Backend session revocation failed.",
      extra: { local_cookie_cleared: false, backend_revoked: false },
    });
  }

  return bffJsonResponse(
    {
      local_cookie_cleared: true,
      backend_revoked: true,
    },
    {
      status: 200,
      setCookieHeader: buildClearRefreshCookieHeader({ isProduction: runtime.isProduction }),
    }
  );
}
