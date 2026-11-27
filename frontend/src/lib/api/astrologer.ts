import { ApiClientError, apiRequest, type ApiClientConfig } from "./client.ts";

export interface AstrologerApplication {
  display_name: string;
  credentials: string;
  tradition: string;
}

export function validateApplication(input: AstrologerApplication) {
  const payload = {
    display_name: input.display_name.trim(),
    credentials: input.credentials.trim(),
    tradition: input.tradition.trim(),
  };
  const validLength = (value: string, min: number, max = Infinity) =>
    [...value].length >= min && [...value].length <= max;
  const errors = {
    display_name: !validLength(payload.display_name, 2, 100),
    credentials: !validLength(payload.credentials, 10),
    tradition: !validLength(payload.tradition, 2, 100),
  };
  return { payload, errors };
}

export type AstrologerIssue = "auth" | "forbidden" | "duplicate" | "validation" | "unavailable";

export function astrologerIssue(error: unknown): AstrologerIssue {
  if (!(error instanceof ApiClientError)) return "unavailable";
  if (error.status === 401) return "auth";
  if (error.status === 403) return "forbidden";
  if (error.status === 422) return "validation";
  if (error.status === 400 && error.message === "Application already submitted") return "duplicate";
  return "unavailable";
}

export async function submitAstrologerApplication(
  config: ApiClientConfig,
  userId: string,
  input: AstrologerApplication,
  signal?: AbortSignal,
): Promise<AstrologerApplication> {
  const { payload } = validateApplication(input);
  const result = await apiRequest<unknown>("/astrologer/apply", { method: "POST", body: payload, config, signal });
  if (
    !result || typeof result !== "object" ||
    !("user_id" in result) || result.user_id !== userId ||
    !("status" in result) || result.status !== "pending" ||
    !("display_name" in result) || typeof result.display_name !== "string" ||
    !("credentials" in result) || typeof result.credentials !== "string" ||
    !("tradition" in result) || typeof result.tradition !== "string"
  ) {
    throw new Error("Unexpected astrologer application response.");
  }
  return {
    display_name: result.display_name, credentials: result.credentials, tradition: result.tradition,
  };
}

export async function verifyReviewAccess(config: ApiClientConfig, signal?: AbortSignal): Promise<void> {
  const result = await apiRequest<unknown>("/review/queue", { config, signal });
  // The current stub has no review-record contract. Discard every unexpected payload.
  if (!Array.isArray(result) || result.length !== 0) {
    throw new Error("Review payload does not match the supported empty stub.");
  }
}
