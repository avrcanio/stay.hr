import { NextResponse } from "next/server";
import { RECEPTION_TOKEN_COOKIE } from "@/lib/types";
import { stayFetch } from "@/lib/stay-server";
import type { AppConfig } from "@/lib/types";

export async function POST(request: Request) {
  let body: { token?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const token = (body.token || "").trim();
  if (!token) {
    return NextResponse.json({ error: "Token required" }, { status: 400 });
  }

  try {
    await stayFetch<AppConfig>("/api/v1/app/config", { token });
  } catch {
    return NextResponse.json({ error: "Invalid device token" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(RECEPTION_TOKEN_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
  });
  return res;
}
