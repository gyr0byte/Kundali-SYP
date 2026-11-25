export const AUTH_BROADCAST_CHANNEL = "kundali-auth";
export const AUTH_WEB_LOCK_NAME = "kundali-auth-refresh";
export const DEFAULT_REFRESH_LEEWAY_MS = 60_000;

const CSRF_HEADER_NAME = "X-Kundali-CSRF";
const CSRF_HEADER_VALUE = "1";

export type AuthSessionStatus =
  | "checking"
  | "authenticated"
  | "unauthenticated"
  | "unavailable";

export interface AuthSessionUser {
  id: string;
  email: string;
  role: string;
  language: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthSessionError {
  code: string;
  status: number | null;
  message: string;
  validationMessages?: readonly string[];
  retryable: boolean;
}

export interface AuthSessionSnapshot {
  status: AuthSessionStatus;
  user: AuthSessionUser | null;
  isAuthenticated: boolean;
  error: AuthSessionError | null;
  hasRecoverableSession: boolean;
}

export interface AuthMutationResult {
  ok: boolean;
  status: number | null;
  code?: string;
  message?: string;
  validationMessages?: readonly string[];
  user?: AuthSessionUser | null;
  sessionEstablished?: boolean;
  retryAfter?: string | null;
  retryAfterSeconds?: number | null;
}

export interface LogoutResult {
  localCookieCleared: boolean;
  backendLogoutRequestCompleted: boolean;
  backendRevocationState:
    | "logout_request_accepted"
    | "missing_cookie"
    | "backend_unconfirmed"
    | "network_error";
}

export interface LogoutAllResult {
  ok: boolean;
  status: number | null;
  localCookieCleared: boolean;
  backendLogoutRequestCompleted: boolean;
  backendRevocationState:
    | "all_refresh_tokens_revoked"
    | "unauthenticated"
    | "backend_rejected"
    | "backend_unconfirmed"
    | "network_error";
  message?: string;
}

export interface BroadcastChannelLike {
  postMessage(message: unknown): void;
  close(): void;
  addEventListener(type: "message", listener: (event: { data: unknown }) => void): void;
  removeEventListener(type: "message", listener: (event: { data: unknown }) => void): void;
}

export interface WebLockManagerLike {
  request<T>(name: string, callback: () => Promise<T>): Promise<T>;
}

export interface AuthSessionManagerConfig {
  bffBasePath?: string;
  refreshLeewayMs?: number;
  fetchImpl?: typeof fetch;
  now?: () => number;
  broadcastChannelFactory?: (channelName: string) => BroadcastChannelLike | null;
  locks?: WebLockManagerLike | null;
}

export interface AuthSessionManager {
  getSnapshot(): AuthSessionSnapshot;
  subscribe(listener: (snapshot: AuthSessionSnapshot) => void): () => void;
  bootstrap(): Promise<AuthSessionSnapshot>;
  getAccessToken(): Promise<string | null>;
  refreshSession(options?: { force?: boolean }): Promise<string | null>;
  refreshOnUnauthorized(failedToken?: string): Promise<string | null>;
  retrySession(): Promise<AuthSessionSnapshot>;
  register(email: string, password: string): Promise<AuthMutationResult>;
  login(email: string, password: string): Promise<AuthMutationResult>;
  logout(): Promise<LogoutResult>;
  logoutAll(): Promise<LogoutAllResult>;
  dispose(): void;
}

interface ValidatedSessionBroadcast {
  type: "SESSION_UPDATED";
  senderId: string;
  user: AuthSessionUser;
  accessToken: string;
  expiresAtMs: number | null;
}

interface ValidatedLogoutBroadcast {
  type: "LOGOUT";
  senderId: string;
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseValidAuthSessionUser(value: unknown): AuthSessionUser | null {
  if (!isPlainRecord(value)) {
    return null;
  }
  const id = typeof value.id === "string" ? value.id.trim() : "";
  const email = typeof value.email === "string" ? value.email.trim() : "";
  const role = typeof value.role === "string" ? value.role.trim() : "";
  const language = typeof value.language === "string" ? value.language.trim() : "";
  const isActive = typeof value.is_active === "boolean" ? value.is_active : null;
  const createdAt = typeof value.created_at === "string" ? value.created_at.trim() : "";
  if (!id || !email || !role || !language || isActive === null || !createdAt) {
    return null;
  }
  return {
    id,
    email,
    role,
    language,
    is_active: isActive,
    created_at: createdAt,
  };
}

function containsForbiddenTokenKey(value: unknown, depth = 0): boolean {
  if (depth > 8 || !value || typeof value !== "object") {
    return false;
  }
  if (Array.isArray(value)) {
    return value.some((item) => containsForbiddenTokenKey(item, depth + 1));
  }
  const record = value as Record<string, unknown>;
  if ("refresh_token" in record || "refreshToken" in record) {
    return true;
  }
  for (const nested of Object.values(record)) {
    if (containsForbiddenTokenKey(nested, depth + 1)) {
      return true;
    }
  }
  return false;
}

function decodeBase64UrlText(input: string): string | null {
  const padded = input.replace(/-/g, "+").replace(/_/g, "/").padEnd(
    Math.ceil(input.length / 4) * 4,
    "="
  );
  try {
    if (typeof atob === "function") {
      return atob(padded);
    }
    if (typeof Buffer !== "undefined") {
      return Buffer.from(padded, "base64").toString("utf8");
    }
  } catch {
    return null;
  }
  return null;
}

function isValidBase64UrlSegment(segment: string): boolean {
  return segment.length > 0 && /^[A-Za-z0-9_-]+$/.test(segment);
}

/**
 * Inspects unverified JWT structure and expiration claim strictly for client-side
 * lifetime checks. Signature verification remains solely the backend's responsibility.
 */
function parseJwtExpirationMs(token: string): number | null {
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }
  const [rawHeader, rawPayload, rawSignature] = parts;
  if (
    !isValidBase64UrlSegment(rawHeader) ||
    !isValidBase64UrlSegment(rawPayload) ||
    !isValidBase64UrlSegment(rawSignature)
  ) {
    return null;
  }
  const decodedHeader = decodeBase64UrlText(rawHeader);
  const decodedPayload = decodeBase64UrlText(rawPayload);
  if (!decodedHeader || !decodedPayload) {
    return null;
  }
  try {
    const header = JSON.parse(decodedHeader);
    const payload = JSON.parse(decodedPayload);
    if (!isPlainRecord(header) || !isPlainRecord(payload)) {
      return null;
    }
    if (typeof header.alg !== "string" || !header.alg.trim()) {
      return null;
    }
    if (typeof payload.exp !== "number" || !Number.isFinite(payload.exp) || payload.exp <= 0) {
      return null;
    }
    return payload.exp * 1000;
  } catch {
    return null;
  }
}

function extractJwtExpiresAtMs(token: string): number | null {
  return parseJwtExpirationMs(token);
}

function extractRetryAfter(
  response: Response,
  currentNowMs: number
): { retryAfter: string | null; retryAfterSeconds: number | null } {
  const raw = response.headers?.get("retry-after")?.trim() || null;
  if (!raw) {
    return { retryAfter: null, retryAfterSeconds: null };
  }
  if (/^\d+$/.test(raw)) {
    const seconds = Number.parseInt(raw, 10);
    return {
      retryAfter: raw,
      retryAfterSeconds: Number.isFinite(seconds) && seconds >= 0 ? seconds : null,
    };
  }
  const targetMs = Date.parse(raw);
  if (Number.isFinite(targetMs)) {
    return {
      retryAfter: raw,
      retryAfterSeconds: Math.max(0, Math.ceil((targetMs - currentNowMs) / 1000)),
    };
  }
  return { retryAfter: raw, retryAfterSeconds: null };
}

function parseSessionBroadcast(
  raw: unknown,
  currentNowMs: number
): ValidatedSessionBroadcast | ValidatedLogoutBroadcast | null {
  if (!isPlainRecord(raw) || containsForbiddenTokenKey(raw)) {
    return null;
  }
  if (typeof raw.type !== "string") {
    return null;
  }
  const senderId = typeof raw.senderId === "string" ? raw.senderId : "";

  if (raw.type === "LOGOUT") {
    return { type: "LOGOUT", senderId };
  }

  if (raw.type === "SESSION_UPDATED") {
    const validUser = parseValidAuthSessionUser(raw.user);
    if (!validUser) {
      return null;
    }
    if (typeof raw.accessToken !== "string" || !raw.accessToken.trim()) {
      return null;
    }
    const trimmedToken = raw.accessToken.trim();
    const jwtExpiresAtMs = parseJwtExpirationMs(trimmedToken);
    if (jwtExpiresAtMs === null || jwtExpiresAtMs <= currentNowMs) {
      return null;
    }
    if (
      typeof raw.expiresAtMs !== "number" ||
      !Number.isFinite(raw.expiresAtMs) ||
      raw.expiresAtMs <= currentNowMs ||
      raw.expiresAtMs > jwtExpiresAtMs + 1000
    ) {
      return null;
    }
    return {
      type: "SESSION_UPDATED",
      senderId,
      user: validUser,
      accessToken: trimmedToken,
      expiresAtMs: Math.min(raw.expiresAtMs, jwtExpiresAtMs),
    };
  }

  return null;
}

function generateInstanceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `tab_${Math.random().toString(36).slice(2)}_${Date.now().toString(36)}`;
}

async function safeParseJson(response: Response): Promise<Record<string, unknown> | null> {
  try {
    const parsed = await response.json();
    return isPlainRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function readValidationMessages(body: Record<string, unknown> | null): string[] | undefined {
  if (!body || !Array.isArray(body.validationMessages)) {
    return undefined;
  }
  const valid = body.validationMessages.filter(
    (entry): entry is string => typeof entry === "string" && entry.trim().length > 0
  );
  return valid.length > 0 ? valid : undefined;
}

function readStringField(
  body: Record<string, unknown> | null,
  key: string,
  fallback: string
): string {
  const val = body?.[key];
  return typeof val === "string" && val.trim() ? val.trim() : fallback;
}

/**
 * Creates a framework-agnostic in-memory session manager coordinating bootstrap,
 * single-flight access-token refresh, cross-tab sync, and honest BFF auth mutations.
 */
export function createAuthSessionManager(
  config: AuthSessionManagerConfig = {}
): AuthSessionManager {
  const bffBasePath = (config.bffBasePath ?? "/api/auth").replace(/\/+$/, "") || "/api/auth";
  const leewayMs = config.refreshLeewayMs ?? DEFAULT_REFRESH_LEEWAY_MS;
  const now = config.now ?? (() => Date.now());
  let instanceId: string | null = null;

  function getInstanceId(): string {
    if (!instanceId) {
      instanceId = generateInstanceId();
    }
    return instanceId;
  }

  // Strictly volatile in-memory session state. Refresh tokens never live here.
  let accessToken: string | null = null;
  let expiresAtMs: number | null = null;
  let user: AuthSessionUser | null = null;
  let status: AuthSessionStatus = "checking";
  let error: AuthSessionError | null = null;
  let hasRecoverableSession = false;

  let inFlightBootstrapPromise: Promise<AuthSessionSnapshot> | null = null;
  let inFlightRefreshPromise: Promise<string | null> | null = null;
  let inTabQueueTail: Promise<void> = Promise.resolve();
  let sessionEpoch = 0;
  let pendingLogoutCount = 0;

  const listeners = new Set<(snapshot: AuthSessionSnapshot) => void>();
  let snapshotCache: AuthSessionSnapshot = {
    status,
    user,
    isAuthenticated: false,
    error,
    hasRecoverableSession,
  };

  function getFetchFn(): typeof fetch | null {
    if (config.fetchImpl) {
      return config.fetchImpl;
    }
    return typeof globalThis.fetch === "function" ? globalThis.fetch : null;
  }

  function resolveLockManager(): WebLockManagerLike | null {
    if (config.locks !== undefined) {
      return config.locks;
    }
    if (typeof navigator !== "undefined" && navigator.locks) {
      return navigator.locks;
    }
    return null;
  }

  function updateSnapshot(): AuthSessionSnapshot {
    snapshotCache = {
      status,
      user,
      isAuthenticated: status === "authenticated" && accessToken !== null && user !== null,
      error,
      hasRecoverableSession,
    };
    return snapshotCache;
  }

  function emit(): void {
    const next = updateSnapshot();
    for (const listener of listeners) {
      listener(next);
    }
  }

  function isTokenUnexpired(referenceNow: number, bufferMs: number): boolean {
    if (!accessToken) {
      return false;
    }
    if (expiresAtMs === null) {
      return true;
    }
    return expiresAtMs - bufferMs > referenceNow;
  }

  function clearMemorySession(nextStatus: AuthSessionStatus, nextError: AuthSessionError | null): void {
    accessToken = null;
    expiresAtMs = null;
    user = null;
    hasRecoverableSession = false;
    status = nextStatus;
    error = nextError;
  }

  function installAuthenticatedSession(
    nextToken: string,
    nextUser: AuthSessionUser,
    nextExpiresAtMs: number | null
  ): void {
    accessToken = nextToken;
    expiresAtMs = nextExpiresAtMs;
    user = nextUser;
    hasRecoverableSession = true;
    status = "authenticated";
    error = null;
  }

  // BroadcastChannel setup: use explicit factory when provided (e.g. tests), otherwise
  // only auto-connect in real browser contexts so SSR / build workers never leak channels.
  let channel: BroadcastChannelLike | null = null;
  if (config.broadcastChannelFactory) {
    channel = config.broadcastChannelFactory(AUTH_BROADCAST_CHANNEL);
  } else if (typeof window !== "undefined" && typeof BroadcastChannel === "function") {
    try {
      channel = new BroadcastChannel(AUTH_BROADCAST_CHANNEL);
    } catch {
      channel = null;
    }
  }

  const handleChannelMessage = (event: { data: unknown }): void => {
    const parsed = parseSessionBroadcast(event?.data, now());
    if (!parsed || parsed.senderId === getInstanceId()) {
      return;
    }
    if (parsed.type === "LOGOUT") {
      sessionEpoch += 1;
      clearMemorySession("unauthenticated", null);
      emit();
      return;
    }
    if (pendingLogoutCount > 0) {
      return;
    }
    installAuthenticatedSession(parsed.accessToken, parsed.user, parsed.expiresAtMs);
    emit();
  };

  if (channel) {
    channel.addEventListener("message", handleChannelMessage);
  }

  function broadcastLogout(): void {
    try {
      channel?.postMessage({ type: "LOGOUT", senderId: getInstanceId() });
    } catch {
      // Channel closed or unavailable
    }
  }

  function broadcastSessionUpdated(): void {
    if (!accessToken || !user) {
      return;
    }
    try {
      channel?.postMessage({
        type: "SESSION_UPDATED",
        senderId: getInstanceId(),
        user,
        accessToken,
        expiresAtMs,
      });
    } catch {
      // Channel closed or unavailable
    }
  }

  async function runWithSessionOperationLock<T>(operation: () => Promise<T>): Promise<T> {
    const locks = resolveLockManager();
    const executeLocked = async (): Promise<T> => {
      if (locks) {
        return locks.request(AUTH_WEB_LOCK_NAME, operation);
      }
      // In-tab fallback when Web Locks API is unsupported: inTabQueueTail strictly serializes
      // refresh, login, logout, and logout-all within this tab, though cross-tab serialization
      // cannot be guaranteed without Web Locks support.
      return operation();
    };

    const previous = inTabQueueTail;
    let releaseCurrent!: () => void;
    inTabQueueTail = new Promise<void>((resolve) => {
      releaseCurrent = resolve;
    });

    await previous;
    try {
      return await executeLocked();
    } finally {
      releaseCurrent();
    }
  }

  async function callBff(
    endpoint: string,
    init: { method: "POST"; body?: unknown; bearerToken?: string }
  ): Promise<{ response: Response; body: Record<string, unknown> | null } | null> {
    const fetchFn = getFetchFn();
    if (!fetchFn) {
      return null;
    }
    const headers: Record<string, string> = {
      Accept: "application/json",
      [CSRF_HEADER_NAME]: CSRF_HEADER_VALUE,
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
      const response = await fetchFn(`${bffBasePath}${endpoint}`, {
        method: init.method,
        headers,
        body: serializedBody,
        credentials: "same-origin",
      });
      const body = await safeParseJson(response);
      return { response, body };
    } catch {
      return null;
    }
  }

  function handleTemporaryRefreshFailure(
    force: boolean,
    upstreamStatus: number | null,
    message: string,
    rotatedHint: boolean
  ): string | null {
    if (rotatedHint) {
      hasRecoverableSession = true;
    }
    if (!force && isTokenUnexpired(now(), 0) && user !== null) {
      // Proactive refresh hit a transient failure while the in-memory token is still valid.
      status = "authenticated";
      error = null;
      emit();
      return accessToken;
    }
    accessToken = null;
    expiresAtMs = null;
    status = "unavailable";
    error = {
      code: "BACKEND_UNAVAILABLE",
      status: upstreamStatus,
      message,
      retryable: true,
    };
    emit();
    return null;
  }

  async function executeLockedRefresh(
    force: boolean,
    tokenSnapshotBeforeLock: string | null,
    requestEpoch: number
  ): Promise<string | null> {
    if (pendingLogoutCount > 0 || requestEpoch !== sessionEpoch) {
      return null;
    }

    // Re-check inside Web Lock: another tab may have completed refresh and broadcast
    // the fresh token via BroadcastChannel while this tab waited on the lock.
    if (!force && isTokenUnexpired(now(), leewayMs) && user !== null) {
      status = "authenticated";
      error = null;
      emit();
      return accessToken;
    }
    if (
      force &&
      accessToken !== null &&
      accessToken !== tokenSnapshotBeforeLock &&
      isTokenUnexpired(now(), 0) &&
      user !== null
    ) {
      status = "authenticated";
      error = null;
      emit();
      return accessToken;
    }

    const upstream = await callBff("/refresh", { method: "POST" });
    if (pendingLogoutCount > 0 || requestEpoch !== sessionEpoch) {
      // Logout or session invalidation occurred while refresh was in flight.
      // Do not install authenticated state or broadcast SESSION_UPDATED;
      // any queued logout will run next under the lock and revoke the latest cookie.
      return null;
    }

    if (!upstream) {
      return handleTemporaryRefreshFailure(
        force,
        null,
        "Authentication service is temporarily unavailable.",
        false
      );
    }

    const { response, body } = upstream;
    const rotatedHint = body?.rotated === true;

    if (response.status >= 500 || response.status === 429) {
      return handleTemporaryRefreshFailure(
        force,
        response.status,
        readStringField(body, "message", "Authentication service is temporarily unavailable."),
        rotatedHint
      );
    }

    if (response.status === 401 || response.status === 403) {
      sessionEpoch += 1;
      clearMemorySession("unauthenticated", {
        code: readStringField(body, "code", "UNAUTHORIZED"),
        status: response.status,
        message: readStringField(body, "message", "Your session has expired. Please sign in again."),
        retryable: false,
      });
      emit();
      broadcastLogout();
      return null;
    }

    if (response.ok && body?.authenticated === false) {
      const hadActiveState = user !== null || accessToken !== null || hasRecoverableSession;
      if (hadActiveState) {
        sessionEpoch += 1;
      }
      clearMemorySession("unauthenticated", null);
      emit();
      if (hadActiveState) {
        broadcastLogout();
      }
      return null;
    }

    if (response.ok && body?.authenticated === true) {
      const nextToken = typeof body.access_token === "string" ? body.access_token.trim() : "";
      const nextUser = parseValidAuthSessionUser(body.user);
      if (nextToken && nextUser) {
        const rawExp =
          typeof body.expires_at_ms === "number"
            ? body.expires_at_ms
            : typeof body.expires_at === "number"
              ? body.expires_at
              : null;
        const jwtExp = extractJwtExpiresAtMs(nextToken);
        const finiteRawExp = rawExp !== null && Number.isFinite(rawExp) ? rawExp : null;
        const nextExpiry =
          jwtExp !== null && finiteRawExp !== null
            ? Math.min(finiteRawExp, jwtExp)
            : (jwtExp ?? finiteRawExp);
        installAuthenticatedSession(nextToken, nextUser, nextExpiry);
        emit();
        broadcastSessionUpdated();
        return accessToken;
      }
    }

    return handleTemporaryRefreshFailure(
      force,
      response.status,
      "Unexpected response from session refresh endpoint.",
      rotatedHint
    );
  }

  async function refreshSession(options: { force?: boolean } = {}): Promise<string | null> {
    if (pendingLogoutCount > 0) {
      return null;
    }

    const force = Boolean(options.force);
    if (!force && isTokenUnexpired(now(), leewayMs) && user !== null) {
      if (status !== "authenticated") {
        status = "authenticated";
        error = null;
        emit();
      }
      return accessToken;
    }

    if (inFlightRefreshPromise) {
      return inFlightRefreshPromise;
    }

    const tokenSnapshotBeforeWait = accessToken;
    const epochAtEnqueue = sessionEpoch;
    let promise: Promise<string | null> | null = null;
    promise = (async () => {
      try {
        return await runWithSessionOperationLock(() =>
          executeLockedRefresh(force, tokenSnapshotBeforeWait, epochAtEnqueue)
        );
      } finally {
        if (inFlightRefreshPromise === promise) {
          inFlightRefreshPromise = null;
        }
      }
    })();

    inFlightRefreshPromise = promise;
    return promise;
  }

  async function bootstrap(): Promise<AuthSessionSnapshot> {
    if (isTokenUnexpired(now(), leewayMs) && user !== null) {
      if (status !== "authenticated") {
        status = "authenticated";
        error = null;
        emit();
      }
      return snapshotCache;
    }

    if (inFlightBootstrapPromise) {
      return inFlightBootstrapPromise;
    }

    let promise: Promise<AuthSessionSnapshot> | null = null;
    promise = (async () => {
      try {
        await refreshSession({ force: false });
        return snapshotCache;
      } finally {
        if (inFlightBootstrapPromise === promise) {
          inFlightBootstrapPromise = null;
        }
      }
    })();

    inFlightBootstrapPromise = promise;
    return promise;
  }

  async function getAccessToken(): Promise<string | null> {
    if (status === "checking" || inFlightBootstrapPromise) {
      await bootstrap();
    }
    if (isTokenUnexpired(now(), leewayMs) && user !== null) {
      return accessToken;
    }
    if (status === "unauthenticated" && !hasRecoverableSession) {
      return null;
    }
    return refreshSession({ force: false });
  }

  async function refreshOnUnauthorized(failedToken?: string): Promise<string | null> {
    const trimmedFailed = typeof failedToken === "string" ? failedToken.trim() : "";
    if (
      trimmedFailed &&
      accessToken !== null &&
      accessToken !== trimmedFailed &&
      isTokenUnexpired(now(), leewayMs) &&
      user !== null
    ) {
      return accessToken;
    }
    return refreshSession({ force: true });
  }

  async function retrySession(): Promise<AuthSessionSnapshot> {
    if (status === "unavailable") {
      status = "checking";
      error = null;
      emit();
    }
    await refreshSession({ force: true });
    return snapshotCache;
  }

  async function register(email: string, password: string): Promise<AuthMutationResult> {
    const upstream = await callBff("/register", {
      method: "POST",
      body: { email, password },
    });
    if (!upstream) {
      return {
        ok: false,
        status: 503,
        code: "BACKEND_UNAVAILABLE",
        message: "Authentication service is temporarily unavailable.",
      };
    }

    const { response, body } = upstream;
    if (response.ok) {
      const parsedUser = parseValidAuthSessionUser(body);
      if (!parsedUser) {
        return {
          ok: false,
          status: 502,
          code: "INVALID_BACKEND_RESPONSE",
          message: "Received an invalid registration response from authentication service.",
        };
      }
      return {
        ok: true,
        status: response.status,
        user: parsedUser,
      };
    }

    const { retryAfter, retryAfterSeconds } = extractRetryAfter(response, now());
    return {
      ok: false,
      status: response.status,
      code: readStringField(body, "code", "REGISTER_FAILED"),
      message: readStringField(body, "message", "Registration could not be completed."),
      validationMessages: readValidationMessages(body),
      retryAfter,
      retryAfterSeconds,
    };
  }

  async function login(email: string, password: string): Promise<AuthMutationResult> {
    const epochAtStart = sessionEpoch;
    return runWithSessionOperationLock(async () => {
      if (pendingLogoutCount > 0 || epochAtStart !== sessionEpoch) {
        return {
          ok: false,
          status: 409,
          code: "SESSION_INVALIDATED",
          message: "Sign-in was superseded by a session sign-out request.",
          sessionEstablished: false,
        };
      }

      const upstream = await callBff("/login", {
        method: "POST",
        body: { email, password },
      });
      if (!upstream) {
        return {
          ok: false,
          status: 503,
          code: "BACKEND_UNAVAILABLE",
          message: "Authentication service is temporarily unavailable.",
        };
      }

      const { response, body } = upstream;
      if (response.ok && body?.authenticated === true) {
        const nextToken = typeof body.access_token === "string" ? body.access_token.trim() : "";
        const nextUser = parseValidAuthSessionUser(body.user);
        if (nextToken && nextUser) {
          const rawExp =
            typeof body.expires_at_ms === "number"
              ? body.expires_at_ms
              : typeof body.expires_at === "number"
                ? body.expires_at
                : null;
          const jwtExp = extractJwtExpiresAtMs(nextToken);
          const finiteRawExp = rawExp !== null && Number.isFinite(rawExp) ? rawExp : null;
          const nextExpiry =
            jwtExp !== null && finiteRawExp !== null
              ? Math.min(finiteRawExp, jwtExp)
              : (jwtExp ?? finiteRawExp);
          sessionEpoch += 1;
          installAuthenticatedSession(nextToken, nextUser, nextExpiry);
          emit();
          broadcastSessionUpdated();
          return {
            ok: true,
            status: 200,
            user: nextUser,
            sessionEstablished: true,
          };
        }
      }

      // Controlled single recovery attempt if BFF established the refresh cookie on login
      // before /me encountered a temporary failure.
      if (body?.session_established === true) {
        hasRecoverableSession = true;
        const recoveryEpoch = sessionEpoch;
        const recoveredToken = await executeLockedRefresh(true, null, recoveryEpoch);
        if (recoveredToken && user) {
          return {
            ok: true,
            status: 200,
            user,
            sessionEstablished: true,
          };
        }
        return {
          ok: false,
          status: response.status,
          code: "SESSION_RECOVERY_UNAVAILABLE",
          message:
            error?.message ??
            "Sign-in cookie was saved, but session profile could not be loaded yet. Please retry.",
          sessionEstablished: true,
        };
      }

      const { retryAfter, retryAfterSeconds } = extractRetryAfter(response, now());
      return {
        ok: false,
        status: response.status,
        code: readStringField(body, "code", "LOGIN_FAILED"),
        message: readStringField(body, "message", "Sign in could not be completed."),
        validationMessages: readValidationMessages(body),
        sessionEstablished: false,
        retryAfter,
        retryAfterSeconds,
      };
    });
  }

  async function logout(): Promise<LogoutResult> {
    pendingLogoutCount += 1;
    sessionEpoch += 1;

    try {
      return await runWithSessionOperationLock(async () => {
        const upstream = await callBff("/logout", { method: "POST" });

        clearMemorySession("unauthenticated", null);
        emit();
        // Broadcast final LOGOUT after lock-protected cookie clearing completes so any
        // earlier refresh cannot immediately re-authenticate peer tabs.
        broadcastLogout();

        if (!upstream) {
          return {
            localCookieCleared: false,
            backendLogoutRequestCompleted: false,
            backendRevocationState: "network_error",
          };
        }

        const { body } = upstream;
        const rawState = body?.backend_revocation_state;
        const backendRevocationState: LogoutResult["backendRevocationState"] =
          rawState === "logout_request_accepted" ||
          rawState === "missing_cookie" ||
          rawState === "backend_unconfirmed"
            ? rawState
            : "backend_unconfirmed";

        return {
          localCookieCleared: body?.local_cookie_cleared === true,
          backendLogoutRequestCompleted: body?.backend_logout_request_completed === true,
          backendRevocationState,
        };
      });
    } finally {
      pendingLogoutCount = Math.max(0, pendingLogoutCount - 1);
    }
  }

  function buildFailedLogoutAllResult(
    upstream: { response: Response; body: Record<string, unknown> | null } | null
  ): LogoutAllResult {
    if (!upstream) {
      return {
        ok: false,
        status: 503,
        localCookieCleared: false,
        backendLogoutRequestCompleted: false,
        backendRevocationState: "network_error",
        message: "Authentication service is temporarily unavailable.",
      };
    }

    const { response, body } = upstream;
    const rawState = body?.backend_revocation_state;
    const backendRevocationState: LogoutAllResult["backendRevocationState"] =
      rawState === "unauthenticated" ||
      rawState === "backend_rejected" ||
      rawState === "backend_unconfirmed"
        ? rawState
        : "backend_unconfirmed";

    return {
      ok: false,
      status: response.status,
      localCookieCleared: body?.local_cookie_cleared === true,
      backendLogoutRequestCompleted: false,
      backendRevocationState,
      message: readStringField(
        body,
        "message",
        "Unable to confirm revocation of all active sessions."
      ),
    };
  }

  function completeConfirmedLogoutAll(httpStatus: number): LogoutAllResult {
    sessionEpoch += 1;
    clearMemorySession("unauthenticated", null);
    emit();
    broadcastLogout();
    return {
      ok: true,
      status: httpStatus,
      localCookieCleared: true,
      backendLogoutRequestCompleted: true,
      backendRevocationState: "all_refresh_tokens_revoked",
    };
  }

  async function logoutAll(): Promise<LogoutAllResult> {
    const token = await getAccessToken();
    if (!token) {
      return {
        ok: false,
        status: 401,
        localCookieCleared: false,
        backendLogoutRequestCompleted: false,
        backendRevocationState: "unauthenticated",
        message: "Authentication required before revoking all sessions.",
      };
    }

    const firstAttempt = await runWithSessionOperationLock(
      async (): Promise<
        | { kind: "done"; result: LogoutAllResult }
        | { kind: "retry401"; failedToken: string }
      > => {
        if (
          pendingLogoutCount > 0 ||
          (status === "unauthenticated" && !hasRecoverableSession && accessToken === null)
        ) {
          return {
            kind: "done",
            result: {
              ok: false,
              status: 401,
              localCookieCleared: false,
              backendLogoutRequestCompleted: false,
              backendRevocationState: "unauthenticated",
              message: "Authentication required before revoking all sessions.",
            },
          };
        }

        const activeToken =
          accessToken && isTokenUnexpired(now(), leewayMs) ? accessToken : token;
        const upstream = await callBff("/logout-all", {
          method: "POST",
          bearerToken: activeToken,
        });

        if (
          upstream &&
          upstream.response.ok &&
          upstream.body?.local_cookie_cleared === true &&
          upstream.body?.backend_logout_request_completed === true
        ) {
          return { kind: "done", result: completeConfirmedLogoutAll(upstream.response.status) };
        }

        if (upstream && upstream.response.status === 401) {
          return { kind: "retry401", failedToken: activeToken };
        }

        return { kind: "done", result: buildFailedLogoutAllResult(upstream) };
      }
    );

    if (firstAttempt.kind === "done") {
      return firstAttempt.result;
    }

    // Lock has been released: refresh once before re-acquiring the lock for the single retry.
    const refreshedToken = await refreshOnUnauthorized(firstAttempt.failedToken);
    if (!refreshedToken) {
      return {
        ok: false,
        status: status === "unavailable" ? 503 : 401,
        localCookieCleared: false,
        backendLogoutRequestCompleted: false,
        backendRevocationState:
          status === "unavailable" ? "backend_unconfirmed" : "unauthenticated",
        message:
          error?.message ?? "Session could not be refreshed to confirm global sign-out.",
      };
    }

    return runWithSessionOperationLock(async () => {
      if (
        pendingLogoutCount > 0 ||
        (status === "unauthenticated" && !hasRecoverableSession && accessToken === null)
      ) {
        return {
          ok: false,
          status: 401,
          localCookieCleared: false,
          backendLogoutRequestCompleted: false,
          backendRevocationState: "unauthenticated",
          message: "Session was invalidated before logout-all retry completed.",
        };
      }

      const finalToken = accessToken ?? refreshedToken;
      const retryUpstream = await callBff("/logout-all", {
        method: "POST",
        bearerToken: finalToken,
      });

      if (
        retryUpstream &&
        retryUpstream.response.ok &&
        retryUpstream.body?.local_cookie_cleared === true &&
        retryUpstream.body?.backend_logout_request_completed === true
      ) {
        return completeConfirmedLogoutAll(retryUpstream.response.status);
      }

      return buildFailedLogoutAllResult(retryUpstream);
    });
  }

  return {
    getSnapshot: () => snapshotCache,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    bootstrap,
    getAccessToken,
    refreshSession,
    refreshOnUnauthorized,
    retrySession,
    register,
    login,
    logout,
    logoutAll,
    dispose() {
      listeners.clear();
      if (channel) {
        channel.removeEventListener("message", handleChannelMessage);
        channel.close();
        channel = null;
      }
    },
  };
}
