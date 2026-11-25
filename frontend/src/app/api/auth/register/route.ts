import { handleRegister } from "@/lib/auth/bff";

export async function POST(request: Request): Promise<Response> {
  return handleRegister(request);
}
