import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { RECEPTION_SESSION_COOKIE, RECEPTION_TOKEN_COOKIE } from "@/lib/types";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    pathname.startsWith("/login") ||
    pathname.startsWith("/api/auth") ||
    pathname === "/health"
  ) {
    return NextResponse.next();
  }

  const sessionId = request.cookies.get(RECEPTION_SESSION_COOKIE)?.value;
  const token = request.cookies.get(RECEPTION_TOKEN_COOKIE)?.value;
  if (!sessionId && !token) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", pathname);
    return NextResponse.redirect(login);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|logo\\.png).*)"],
};
