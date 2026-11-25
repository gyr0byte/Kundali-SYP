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

function isValidAuthSessionUser(value: unknown): value is AuthSessionUser {
  if (!isPlainRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    value.id.trim().length > 0 &&
    typeof value.email === "string" &&
    value.email.trim().length > 0 &&
    typeof value.role === "string"
  );
}

function containsForbiddenTokenKey(payload: Record<string, unknown>): boolean {
  if ("refresh_token" in payload || "refreshToken" in payload) {
    return true;
  }
  const user = payload.user;
  if (isPlainRecord(user) && ("refresh_token" in user || "refreshToken" in user)) {
    return true;
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

function extractJwtExpiresAtMs(token: string): number | null {
  const parts = token.split(".");
  if (parts.length !== 3 || !parts[1]) {
    return null;
  }
  const decoded = decodeBase64UrlText(parts[1]);
  if (!decoded) {
    return null;
  }
  try {
    const payload = JSON.parse(decoded) as { exp?: unknown };
    if (typeof payload.exp === "number" && Number.isFinite(payload.exp) && payload.exp > 0) {
      return payload.exp * 1000;
    }
  } catch {
    return null;
  }
  return null;
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
    if (!isValidAuthSessionUser(raw.user)) {
      return null;
    }
    if (typeof raw.accessToken !== "string" || !raw.accessToken.trim()) {
      return null;
    }
    if (
      raw.expiresAtMs !== null &&
      (typeof raw.expiresAtMs !== "number" ||
        !Number.isFinite(raw.expiresAtMs) ||
        raw.expiresAtMs <= currentNowMs)
    ) {
      return null;
    }
    return {
      type: "SESSION_UPDATED",
      senderId,
      user: raw.user,
      accessToken: raw.accessToken.trim(),
      expiresAtMs: raw.expiresAtMs,
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
      clearMemorySession("unauthenticated", null);
      emit();
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

  async function runWithRefreshLock<T>(operation: () => Promise<T>): Promise<T> {
    const locks = resolveLockManager();
    if (locks) {
      return locks.request(AUTH_WEB_LOCK_NAME, operation);
    }
    // Fallback when Web Locks API is unavailable: in-tab single-flight promise still
    // deduplicates concurrent refreshes within this tab, though simultaneous refreshes
    // across separate browser tabs rely on cookie serialization at the BFF/backend.
    return operation();
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
    tokenSnapshotBeforeLock: string | null
  ): Promise<string | null> {
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
      clearMemorySession("unauthenticated", null);
      emit();
      if (hadActiveState) {
        broadcastLogout();
      }
      return null;
    }

    if (response.ok && body?.authenticated === true) {
      const nextToken = typeof body.access_token === "string" ? body.access_token.trim() : "";
      const nextUser = body.user;
      if (nextToken && isValidAuthSessionUser(nextUser)) {
        const nextExpiry =
          typeof body.expires_at_ms === "number" && Number.isFinite(body.expires_at_ms)
            ? body.expires_at_ms
            : extractJwtExpiresAtMs(nextToken);
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
    let promise: Promise<string | null> | null = null;
    promise = (async () => {
      try {
        return await runWithRefreshLock(() =>
          executeLockedRefresh(force, tokenSnapshotBeforeWait)
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
      return {
        ok: true,
        status: response.status,
        user: isValidAuthSessionUser(body?.user) ? body.user : null,
      };
    }

    return {
      ok: false,
      status: response.status,
      code: readStringField(body, "code", "REGISTER_FAILED"),
      message: readStringField(body, "message", "Registration could not be completed."),
      validationMessages: readValidationMessages(body),
    };
  }

  async function login(email: string, password: string): Promise<AuthMutationResult> {
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
      const nextUser = body.user;
      if (nextToken && isValidAuthSessionUser(nextUser)) {
        const nextExpiry =
          typeof body.expires_at_ms === "number" && Number.isFinite(body.expires_at_ms)
            ? body.expires_at_ms
            : extractJwtExpiresAtMs(nextToken);
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
      const recoveredToken = await refreshSession({ force: true });
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

    return {
      ok: false,
      status: response.status,
      code: readStringField(body, "code", "LOGIN_FAILED"),
      message: readStringField(body, "message", "Sign in could not be completed."),
      validationMessages: readValidationMessages(body),
      sessionEstablished: false,
    };
  }

  async function logout(): Promise<LogoutResult> {
    clearMemorySession("unauthenticated", null);
    emit();
    broadcastLogout();

    const upstream = await callBff("/logout", { method: "POST" });
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
  }

  async function logoutAll(): Promise<LogoutAllResult> {
    let token = await getAccessToken();
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

    let upstream = await callBff("/logout-all", { method: "POST", bearerToken: token });
    if (upstream && upstream.response.status === 401) {
      const refreshedToken = await refreshOnUnauthorized(token);
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
      token = refreshedToken;
      upstream = await callBff("/logout-all", { method: "POST", bearerToken: token });
    }

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
    if (
      response.ok &&
      body?.local_cookie_cleared === true &&
      body?.backend_logout_request_completed === true
    ) {
      clearMemorySession("unauthenticated", null);
      emit();
      broadcastLogout();
      return {
        ok: true,
        status: response.status,
        localCookieCleared: true,
        backendLogoutRequestCompleted: true,
        backendRevocationState: "all_refresh_tokens_revoked",
      };
    }

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
