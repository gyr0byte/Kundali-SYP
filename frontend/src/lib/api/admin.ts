import { ApiClientError, apiRequest, type ApiClientConfig } from "./client.ts";

export const roles = ["user", "astrologer", "admin"] as const;
export const astrologerStatuses = ["pending", "approved", "suspended"] as const;
export type AdminRole = (typeof roles)[number];
export type AstrologerStatus = (typeof astrologerStatuses)[number];
export type AdminAction = "deactivate" | "reactivate" | "approve" | "suspend";
export type AdminIssue = "expired" | "forbidden" | "protected" | "stale" | "failed";

export interface AdminUser {
  id: string;
  email: string;
  role: AdminRole;
  is_active: boolean;
  created_at: string;
}

export interface AdminAstrologer {
  user_id: string;
  display_name: string;
  tradition: string;
  status: AstrologerStatus;
  approved_at: string | null;
}

export const auditActions = [
  "auth:register", "auth:lockout", "auth:token_reuse_detected", "auth:password_change",
  "auth:password_reset", "user:deactivate", "user:reactivate", "astrologer:apply",
  "astrologer:approve", "astrologer:suspend", "profile:create", "profile:update", "profile:delete",
] as const;
type AuditAction = (typeof auditActions)[number];
export interface AdminAudit {
  id: string;
  actor_id: string | null;
  action: AuditAction | "other";
  target_type: "user" | "astrologer_profile" | "birth_profile" | "token_family" | null;
  target_id: string | null;
  created_at: string;
}

interface Page<T> { items: T[]; total: number; offset: number; limit: number }
export type AdminQuery =
  | { section: "users"; role?: AdminRole; active?: boolean }
  | { section: "astrologers"; status?: AstrologerStatus }
  | { section: "audit" };
export type AdminRecords =
  | { section: "users"; page: Page<AdminUser> }
  | { section: "astrologers"; page: Page<AdminAstrologer> }
  | { section: "audit"; page: Page<AdminAudit> };

const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const targets = ["user", "astrologer_profile", "birth_profile", "token_family"] as const;

function known<T extends string>(values: readonly T[], value: unknown): T | undefined {
  return values.find((entry) => entry === value);
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid admin response");
  return Object.fromEntries(Object.entries(value));
}

function string(value: unknown): string {
  if (typeof value !== "string") throw new Error("Invalid admin response");
  return value;
}

function id(value: unknown): string {
  const valueString = string(value);
  if (!uuid.test(valueString)) throw new Error("Invalid admin identifier");
  return valueString;
}

function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error("Invalid admin pagination");
  }
  return value;
}

function userRecord(value: unknown): AdminUser {
  const row = object(value);
  const role = known(roles, row.role);
  if (!role || typeof row.is_active !== "boolean") throw new Error("Invalid admin user");
  return { id: id(row.id), email: string(row.email), role, is_active: row.is_active, created_at: string(row.created_at) };
}

function astrologerRecord(value: unknown): AdminAstrologer {
  const row = object(value);
  const status = known(astrologerStatuses, row.status);
  if (!status) throw new Error("Invalid astrologer status");
  // Application free text can contain private documents or unrelated credentials.
  return {
    user_id: id(row.user_id), display_name: string(row.display_name), tradition: string(row.tradition),
    status, approved_at: row.approved_at == null ? null : string(row.approved_at),
  };
}

function auditRecord(value: unknown): AdminAudit {
  const row = object(value);
  const safeId = (value: unknown) => typeof value === "string" && uuid.test(value) ? value : null;
  const targetType = known(targets, row.target_type) ?? null;
  return {
    id: id(row.id), actor_id: safeId(row.actor_id), action: known(auditActions, row.action) ?? "other",
    target_type: targetType,
    target_id: targetType === "user" || targetType === "astrologer_profile" ? safeId(row.target_id) : null,
    created_at: string(row.created_at),
  };
}

function queryPath(query: AdminQuery, limit: number, offset: number) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (query.section === "users") {
    if (query.role) params.set("role", query.role);
    if (query.active !== undefined) params.set("is_active", String(query.active));
  }
  if (query.section === "astrologers" && query.status) params.set("status", query.status);
  return `/admin/${query.section}?${params}`;
}

export async function fetchAdminRecords(
  config: ApiClientConfig, query: AdminQuery, limit: number, offset: number, signal?: AbortSignal,
): Promise<AdminRecords> {
  const result = object(await apiRequest<unknown>(queryPath(query, limit, offset), { config, signal }));
  if (!Array.isArray(result.items)) throw new Error("Invalid admin collection");
  const pagination = { total: integer(result.total), offset: integer(result.offset), limit: integer(result.limit) };
  if (pagination.offset !== offset || pagination.limit !== limit || result.items.length > limit) {
    throw new Error("Mismatched admin pagination");
  }
  if (query.section === "users") return { section: "users", page: { ...pagination, items: result.items.map(userRecord) } };
  if (query.section === "astrologers") return { section: "astrologers", page: { ...pagination, items: result.items.map(astrologerRecord) } };
  return { section: "audit", page: { ...pagination, items: result.items.map(auditRecord) } };
}

export async function fetchAdminTotals(config: ApiClientConfig, signal?: AbortSignal) {
  const queries: AdminQuery[] = [{ section: "users" }, { section: "astrologers", status: "pending" }, { section: "audit" }];
  return Promise.all(queries.map(async (query) => {
    const result = object(await apiRequest<unknown>(queryPath(query, 1, 0), { config, signal }));
    return integer(result.total);
  }));
}

export async function submitAdminAction(config: ApiClientConfig, action: AdminAction, userId: string, signal?: AbortSignal) {
  const collection = action === "deactivate" || action === "reactivate" ? "users" : "astrologers";
  await apiRequest<null>(`/admin/${collection}/${id(userId)}/${action}`, { method: "POST", config, signal });
}

export function adminIssue(error: unknown): AdminIssue {
  if (!(error instanceof ApiClientError)) return "failed";
  if (error.status === 401) return "expired";
  if (error.status === 403) return "forbidden";
  if (error.status === 404 || error.status === 409) return "stale";
  if (error.status === 400 && ["Cannot deactivate your own account", "Cannot deactivate the last admin"].includes(error.message)) return "protected";
  return "failed";
}
