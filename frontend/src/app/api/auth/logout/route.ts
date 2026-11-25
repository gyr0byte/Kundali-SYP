import { handleLogout } from "@/lib/auth/bff";

export async function POST(request: Request): Promise<Response> {
  return handleLogout(request);
}
