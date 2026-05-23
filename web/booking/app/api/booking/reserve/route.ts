import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { stayFetch } from "@/lib/stay-server";
import type { ReservationCreateResponse } from "@/lib/types";

export async function POST(request: Request) {
  const h = await headers();
  const host = (h.get("x-forwarded-host") || h.get("host") || "").split(":")[0];

  if (!host) {
    return NextResponse.json({ error: "Missing host" }, { status: 400 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  try {
    const result = await stayFetch<ReservationCreateResponse>("/api/v1/public/reservations", {
      host,
      method: "POST",
      body,
    });
    return NextResponse.json(result);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Booking failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
