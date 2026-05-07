import { proxyBackendJson } from "@/lib/backendProxy";

export async function GET(): Promise<Response> {
  return proxyBackendJson("/health");
}
