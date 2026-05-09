import { proxyBackendVideoResponse } from "@/lib/backendProxy";

interface AnalysisVideoRouteContext {
  params: Promise<{
    analysisId: string;
  }>;
}

export async function GET(
  request: Request,
  context: AnalysisVideoRouteContext
): Promise<Response> {
  const { analysisId } = await context.params;
  return proxyBackendVideoResponse(
    `/analyses/${encodeURIComponent(analysisId)}/video`,
    request
  );
}
