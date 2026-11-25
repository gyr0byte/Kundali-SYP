import { handleRefresh } from "@/lib/auth/bff";

/**
 * Rotate the HttpOnly refresh cookie via FastAPI /api/v1/auth/refresh.
 * Note: FastAPI revokes an entire token family upon token reuse; BFF avoids
 * concurrent refreshes per handler invocation while Commit 2 coordinates client tabs.
 */
export async function POST(request: Request): Promise<Response> {
  return handleRefresh(request);
}
