import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getServerToken, stayFetch } from "@/lib/stay-server";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, pathSegments: string[]) {
  const token = await getServerToken();
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const path = `/api/v1/${pathSegments.join("/")}`;
  const url = new URL(request.url);
  const query = url.search;

  const headers: Record<string, string> = {
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
    Host: (process.env.STAY_RECEPTION_HOST || "app.stay.hr").split(":")[0],
  };

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
  const text = await upstream.text();

  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json",
    },
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
