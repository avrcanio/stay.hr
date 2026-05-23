import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { buildStayAuthHeaders } from "@/lib/stay-server";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, pathSegments: string[]) {
  const authHeaders = await buildStayAuthHeaders();
  if (!authHeaders) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const path = `/api/v1/${pathSegments.join("/")}`;
  const url = new URL(request.url);
  const query = url.search;

  const headers: Record<string, string> = { ...authHeaders };

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    const body = await request.text();
    if (body) {
      headers["Content-Type"] = request.headers.get("content-type") || "application/json";
      init.body = body;
    }
  }

  const internal = (process.env.STAY_API_INTERNAL_URL || "http://stay_django:8000").replace(
    /\/+$/,
    "",
  );
  const upstream = await fetch(`${internal}${path}${query}`, init);
  const contentType = upstream.headers.get("content-type") || "application/json";
  const isBinary =
    contentType.startsWith("image/") ||
    contentType.includes("octet-stream") ||
    contentType.startsWith("application/pdf");

  const body = isBinary ? await upstream.arrayBuffer() : await upstream.text();

  const responseHeaders: Record<string, string> = {
    "Content-Type": contentType,
  };
  if (isBinary && upstream.headers.get("cache-control")) {
    responseHeaders["Cache-Control"] = upstream.headers.get("cache-control")!;
  }

  return new NextResponse(body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxy(request, path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxy(request, path);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxy(request, path);
}

export async function PUT(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxy(request, path);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxy(request, path);
}
