import { proxyBackendResponse } from "@/lib/backendProxy";

interface AnalysisVideoRouteContext {
  params: Promise<{
    analysisId: string;
  }>;
}

export async function GET(
  _request: Request,
  context: AnalysisVideoRouteContext
): Promise<Response> {
  const { analysisId } = await context.params;
  return proxyBackendResponse(`/analyses/${encodeURIComponent(analysisId)}/video`);
}
