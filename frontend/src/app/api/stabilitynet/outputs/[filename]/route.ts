import { proxyBackendResponse } from "@/lib/backendProxy";

interface OutputVideoRouteContext {
  params: Promise<{
    filename: string;
  }>;
}

export async function GET(
  _request: Request,
  context: OutputVideoRouteContext
): Promise<Response> {
  const { filename } = await context.params;
  return proxyBackendResponse(`/outputs/${encodeURIComponent(filename)}`);
}
