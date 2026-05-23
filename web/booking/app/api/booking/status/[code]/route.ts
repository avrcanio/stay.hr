import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { stayFetch } from "@/lib/stay-server";
import type { ReservationStatusResponse } from "@/lib/types";

type Params = { params: Promise<{ code: string }> };

export async function GET(_request: Request, { params }: Params) {
  const h = await headers();
  const host = (h.get("x-forwarded-host") || h.get("host") || "").split(":")[0];
  const { code } = await params;

  if (!host) {
    return NextResponse.json({ error: "Missing host" }, { status: 400 });
  }

  try {
    const result = await stayFetch<ReservationStatusResponse>(
      `/api/v1/public/reservations/${encodeURIComponent(code)}`,
      { host },
    );
    return NextResponse.json(result);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Status lookup failed";
    const status = message.includes("404") ? 404 : 502;
    return NextResponse.json({ error: message }, { status });
  }
}
