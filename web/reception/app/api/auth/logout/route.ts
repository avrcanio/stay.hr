import { NextResponse } from "next/server";
import { getServerSessionId, stayLogoutFetch } from "@/lib/stay-server";
import { RECEPTION_SESSION_COOKIE, RECEPTION_TOKEN_COOKIE } from "@/lib/types";

export async function POST() {
  const sessionId = await getServerSessionId();
  if (sessionId) {
    await stayLogoutFetch(sessionId);
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(RECEPTION_SESSION_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  res.cookies.set(RECEPTION_TOKEN_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return res;
}
