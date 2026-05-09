import { NextResponse } from "next/server";

const DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8000";

export async function proxyBackendJson(
  path: string,
  init?: RequestInit
): Promise<NextResponse> {
  const headers = new Headers(init?.headers);
  if (typeof init?.body === "string" && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  try {
    const response = await fetch(backendUrl(path), {
      ...init,
      headers,
      cache: "no-store"
    });
    const body = await response.text();
    const contentType = response.headers.get("content-type") ?? "application/json";

    if (body.length === 0) {
      return new NextResponse(null, { status: response.status });
    }

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "content-type": contentType
      }
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown backend error.";
    return NextResponse.json(
      {
        detail: `Unable to reach StabilityNet backend at ${backendBaseUrl()}.`,
        error: message
      },
      { status: 502 }
    );
  }
}

export async function proxyBackendFormData(
  path: string,
  formData: FormData
): Promise<NextResponse> {
  return proxyBackendRequest(path, {
    method: "POST",
    body: formData
  });
}

export async function proxyBackendResponse(
  path: string,
  init?: RequestInit
): Promise<NextResponse> {
  return proxyBackendRequest(path, init);
}

export async function proxyBackendVideoResponse(
  path: string,
  request: Request
): Promise<NextResponse> {
  const headers = new Headers();
  for (const headerName of ["range", "if-range"]) {
    const value = request.headers.get(headerName);
    if (value !== null) {
      headers.set(headerName, value);
    }
  }

  return proxyBackendRequest(path, { headers });
}

async function proxyBackendRequest(
  path: string,
  init?: RequestInit
): Promise<NextResponse> {
  const headers = new Headers(init?.headers);
  if (typeof init?.body === "string" && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  try {
    const response = await fetch(backendUrl(path), {
      ...init,
      headers,
      cache: "no-store"
    });
    const body = await response.arrayBuffer();

    return new NextResponse(body, {
      status: response.status,
      headers: proxyResponseHeaders(response)
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown backend error.";
    return NextResponse.json(
      {
        detail: `Unable to reach StabilityNet backend at ${backendBaseUrl()}.`,
        error: message
      },
      { status: 502 }
    );
  }
}

function proxyResponseHeaders(response: Response): Headers {
  const headers = new Headers();
  const passthroughHeaders = [
    "accept-ranges",
    "cache-control",
    "content-length",
    "content-range",
    "content-type",
    "etag",
    "last-modified"
  ];

  for (const headerName of passthroughHeaders) {
    const value = response.headers.get(headerName);
    if (value !== null) {
      headers.set(headerName, value);
    }
  }

  if (!headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  return headers;
}

function backendUrl(path: string): string {
  return new URL(path, normalizedBackendBaseUrl()).toString();
}

function normalizedBackendBaseUrl(): string {
  const baseUrl = backendBaseUrl();
  return baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
}

function backendBaseUrl(): string {
  return process.env.STABILITYNET_API_BASE_URL ?? DEFAULT_BACKEND_BASE_URL;
}
