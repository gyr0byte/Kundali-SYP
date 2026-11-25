import type { AccessTokenProvider } from "@/lib/kundali/types";

export const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

export type ApiErrorCode =
  | "AUTH_REQUIRED"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "VALIDATION_ERROR"
  | "BACKEND_UNAVAILABLE"
  | "NETWORK_ERROR"
  | "HTTP_ERROR";

export interface ApiClientConfig {
  getAccessToken?: AccessTokenProvider;
  /**
   * Optional single-shot hook invoked once when a resource endpoint responds HTTP 401.
   * Returning a fresh non-empty access token triggers a single retry; null/empty fails as UNAUTHORIZED.
   */
  onUnauthorizedRefresh?: (failedToken?: string) => Promise<string | null>;
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export class ApiClientError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number | null;
  readonly validationMessages: readonly string[];

  constructor(params: {
    code: ApiErrorCode;
    status: number | null;
    message: string;
    validationMessages?: readonly string[];
  }) {
    super(params.message);
    this.name = "ApiClientError";
    this.code = params.code;
    this.status = params.status;
    this.validationMessages = params.validationMessages ?? [];
  }
}

export function resolveApiBaseUrl(overrideBaseUrl?: string): string {
  const envUrl =
    typeof process !== "undefined" ? process.env.NEXT_PUBLIC_API_BASE_URL : undefined;
  const raw = (overrideBaseUrl ?? envUrl ?? DEFAULT_API_BASE_URL).trim();
  const effective = raw || DEFAULT_API_BASE_URL;
  return effective.replace(/\/+$/, "");
}

function cleanValidationMessage(raw: string): string {
  return raw.replace(/^Value error,\s*/i, "").trim();
}

function extractValidationMessages(body: unknown): string[] {
  if (!body || typeof body !== "object") {
    return [];
  }
  const detail = (body as { detail?: unknown }).detail;
  if (!Array.isArray(detail)) {
    if (typeof detail === "string" && detail.trim()) {
      return [cleanValidationMessage(detail)];
    }
    return [];
  }
  const messages: string[] = [];
  for (const item of detail) {
    if (item && typeof item === "object" && "msg" in item) {
      const msg = (item as { msg?: unknown }).msg;
      if (typeof msg === "string" && msg.trim()) {
        messages.push(cleanValidationMessage(msg));
      }
    }
  }
  return Array.from(new Set(messages));
}

function extractDetailMessage(body: unknown): string | null {
  if (!body || typeof body !== "object") {
    return null;
  }
  const detail = (body as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.trim() ? detail.trim() : null;
}

async function resolveValidToken(getAccessToken?: AccessTokenProvider): Promise<string> {
  if (!getAccessToken) {
    throw new ApiClientError({
      code: "AUTH_REQUIRED",
      status: 401,
      message: "Authentication required before calling backend profile APIs.",
    });
  }
  const token = await getAccessToken();
  const cleaned = typeof token === "string" ? token.trim() : "";
  if (!cleaned) {
    throw new ApiClientError({
      code: "AUTH_REQUIRED",
      status: 401,
      message: "Authentication required before calling backend profile APIs.",
    });
  }
  return cleaned;
}

async function sendAuthorizedFetch(
  url: string,
  method: "GET" | "POST" | "PATCH" | "DELETE",
  serializedBody: string | undefined,
  token: string,
  fetchFn: typeof fetch
): Promise<{ response: Response; parsedBody: unknown }> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (serializedBody !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetchFn(url, {
      method,
      headers,
      body: serializedBody,
      credentials: "omit",
    });
  } catch {
    throw new ApiClientError({
      code: "NETWORK_ERROR",
      status: null,
      message: "Unable to reach the backend API server.",
    });
  }

  let parsedBody: unknown = null;
  if (response.status !== 204) {
    const contentType = response.headers?.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      try {
        parsedBody = await response.json();
      } catch {
        parsedBody = null;
      }
    }
  }

  return { response, parsedBody };
}

function buildApiErrorFromResponse(status: number, parsedBody: unknown): ApiClientError {
  if (status === 401) {
    return new ApiClientError({
      code: "UNAUTHORIZED",
      status: 401,
      message: "Authentication rejected or session token expired.",
    });
  }
  if (status === 403) {
    return new ApiClientError({
      code: "FORBIDDEN",
      status: 403,
      message: "You do not have permission to perform this profile action.",
    });
  }
  if (status === 404) {
    return new ApiClientError({
      code: "NOT_FOUND",
      status: 404,
      message: "Birth profile was not found.",
    });
  }
  if (status === 422) {
    const validationMessages = extractValidationMessages(parsedBody);
    return new ApiClientError({
      code: "VALIDATION_ERROR",
      status: 422,
      message:
        validationMessages[0] ?? "Submitted birth profile data did not pass server validation.",
      validationMessages,
    });
  }
  if (status === 502 || status === 503 || status === 504) {
    return new ApiClientError({
      code: "BACKEND_UNAVAILABLE",
      status,
      message: "Backend service is temporarily unavailable.",
    });
  }
  return new ApiClientError({
    code: "HTTP_ERROR",
    status,
    message: extractDetailMessage(parsedBody) ?? `Request failed with status ${status}.`,
  });
}

export async function apiRequest<T>(
  path: string,
  options: {
    method?: "GET" | "POST" | "PATCH" | "DELETE";
    body?: unknown;
    config?: ApiClientConfig;
  } = {}
): Promise<T> {
  const { method = "GET", body, config = {} } = options;
  // Never issue network requests without an injected access token.
  const token = await resolveValidToken(config.getAccessToken);

  const fetchFn = config.fetchImpl ?? (typeof fetch === "function" ? fetch : null);
  if (!fetchFn) {
    throw new ApiClientError({
      code: "NETWORK_ERROR",
      status: null,
      message: "Fetch implementation unavailable in current environment.",
    });
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${resolveApiBaseUrl(config.baseUrl)}${normalizedPath}`;
  const serializedBody = body !== undefined ? JSON.stringify(body) : undefined;

  let result = await sendAuthorizedFetch(url, method, serializedBody, token, fetchFn);
  if (result.response.status === 401 && config.onUnauthorizedRefresh) {
    let refreshedRaw: string | null = null;
    try {
      refreshedRaw = await config.onUnauthorizedRefresh(token);
    } catch {
      refreshedRaw = null;
    }
    const refreshedToken = typeof refreshedRaw === "string" ? refreshedRaw.trim() : "";
    if (refreshedToken) {
      result = await sendAuthorizedFetch(url, method, serializedBody, refreshedToken, fetchFn);
    }
  }

  if (!result.response.ok) {
    throw buildApiErrorFromResponse(result.response.status, result.parsedBody);
  }

  return result.parsedBody as T;
}
