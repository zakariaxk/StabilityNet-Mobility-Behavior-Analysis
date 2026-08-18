import { proxyBackendJson } from "@/lib/backendProxy";

interface FramesRouteContext {
  params: Promise<{
    analysisId: string;
  }>;
}

/** Full per-frame trace — large, and excluded from the analysis response. */
export async function GET(
  _request: Request,
  context: FramesRouteContext
): Promise<Response> {
  const { analysisId } = await context.params;
  return proxyBackendJson(`/analyses/${encodeURIComponent(analysisId)}/frames`);
}
