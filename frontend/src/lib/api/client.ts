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

  const headers: Record<string, string> = {
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
  };
  let serializedBody: string | undefined;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    serializedBody = JSON.stringify(body);
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

  if (!response.ok) {
    if (response.status === 401) {
      throw new ApiClientError({
        code: "UNAUTHORIZED",
        status: 401,
        message: "Authentication rejected or session token expired.",
      });
    }
    if (response.status === 403) {
      throw new ApiClientError({
        code: "FORBIDDEN",
        status: 403,
        message: "You do not have permission to perform this profile action.",
      });
    }
    if (response.status === 404) {
      throw new ApiClientError({
        code: "NOT_FOUND",
        status: 404,
        message: "Birth profile was not found.",
      });
    }
    if (response.status === 422) {
      const validationMessages = extractValidationMessages(parsedBody);
      throw new ApiClientError({
        code: "VALIDATION_ERROR",
        status: 422,
        message:
          validationMessages[0] ?? "Submitted birth profile data did not pass server validation.",
        validationMessages,
      });
    }
    if (response.status === 502 || response.status === 503 || response.status === 504) {
      throw new ApiClientError({
        code: "BACKEND_UNAVAILABLE",
        status: response.status,
        message: "Backend service is temporarily unavailable.",
      });
    }
    throw new ApiClientError({
      code: "HTTP_ERROR",
      status: response.status,
      message: extractDetailMessage(parsedBody) ?? `Request failed with status ${response.status}.`,
    });
  }

  return parsedBody as T;
}
