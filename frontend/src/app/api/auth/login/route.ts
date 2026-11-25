import { handleLogin } from "@/lib/auth/bff";

export async function POST(request: Request): Promise<Response> {
  return handleLogin(request);
}
