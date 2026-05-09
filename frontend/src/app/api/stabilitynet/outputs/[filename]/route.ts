import { proxyBackendVideoResponse } from "@/lib/backendProxy";

interface OutputVideoRouteContext {
  params: Promise<{
    filename: string;
  }>;
}

export async function GET(
  request: Request,
  context: OutputVideoRouteContext
): Promise<Response> {
  const { filename } = await context.params;
  return proxyBackendVideoResponse(`/outputs/${encodeURIComponent(filename)}`, request);
}
