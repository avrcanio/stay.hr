import { NextResponse } from "next/server";
import { RECEPTION_TOKEN_COOKIE } from "@/lib/types";

export async function POST() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(RECEPTION_TOKEN_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return res;
}
