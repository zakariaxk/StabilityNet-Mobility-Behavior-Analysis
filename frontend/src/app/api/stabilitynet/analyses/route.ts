import { NextResponse } from "next/server";

import { proxyBackendJson } from "@/lib/backendProxy";

export async function POST(request: Request): Promise<Response> {
  let body: unknown;

  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Request body must be JSON." }, { status: 400 });
  }

  return proxyBackendJson("/analyses", {
    method: "POST",
    body: JSON.stringify(body)
  });
}
