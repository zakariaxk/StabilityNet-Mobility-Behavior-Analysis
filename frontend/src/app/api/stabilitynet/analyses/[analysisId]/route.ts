import { proxyBackendJson } from "@/lib/backendProxy";

interface AnalysisRouteContext {
  params: Promise<{
    analysisId: string;
  }>;
}

export async function GET(
  _request: Request,
  context: AnalysisRouteContext
): Promise<Response> {
  const { analysisId } = await context.params;
  return proxyBackendJson(`/analyses/${encodeURIComponent(analysisId)}`);
}
