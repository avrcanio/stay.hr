import { NextResponse } from "next/server";
import { stayFetch } from "@/lib/stay-server";
import type { AppConfig } from "@/lib/types";

export async function GET() {
  try {
    const config = await stayFetch<AppConfig>("/api/v1/app/config");
    return NextResponse.json({
      ok: true,
      tenant: config.tenant.name,
    });
  } catch {
    return NextResponse.json({ ok: false }, { status: 401 });
  }
}
