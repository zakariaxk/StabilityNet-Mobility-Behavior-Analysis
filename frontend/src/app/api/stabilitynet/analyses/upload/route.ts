import { proxyBackendFormData } from "@/lib/backendProxy";

export async function POST(request: Request): Promise<Response> {
  const formData = await request.formData();
  return proxyBackendFormData("/analyses/upload", formData);
}
