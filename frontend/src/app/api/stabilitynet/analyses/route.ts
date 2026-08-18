import { NextResponse } from "next/server";

import { proxyBackendJson } from "@/lib/backendProxy";

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const limit = url.searchParams.get("limit") ?? "50";
  const offset = url.searchParams.get("offset") ?? "0";
  return proxyBackendJson(
    `/analyses?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`
  );
}

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
