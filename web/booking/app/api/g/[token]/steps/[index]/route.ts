import { headers } from "next/headers";
import { NextResponse } from "next/server";

type Params = { params: Promise<{ token: string; index: string }> };

function internalApiBase(): string {
  return (process.env.STAY_API_INTERNAL_URL || "http://stay-django:8000").replace(/\/+$/, "");
}

async function hostHeader(): Promise<string> {
  const h = await headers();
  return (h.get("x-forwarded-host") || h.get("host") || "").split(":")[0];
}

export async function GET(_request: Request, { params }: Params) {
  const { token, index } = await params;
  const host = await hostHeader();
  if (!host) {
    return NextResponse.json({ error: "Missing host" }, { status: 400 });
  }

  const url =
    `${internalApiBase()}/api/v1/public/guest-portal/` +
    `${encodeURIComponent(token)}/steps/${encodeURIComponent(index)}/`;
  const res = await fetch(url, {
    headers: {
      "X-Forwarded-Host": host.split(":")[0].toLowerCase(),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text();
    let data: unknown = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { error: text.slice(0, 200) };
      }
    }
    return NextResponse.json(data, { status: res.status });
  }

  const contentType = res.headers.get("content-type") || "image/jpeg";
  const body = await res.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": contentType,
      "Cache-Control": "no-store, must-revalidate",
    },
  });
}
