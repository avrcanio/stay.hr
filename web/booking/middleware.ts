import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { isValidLocale, LOCALE_COOKIE } from "@/i18n/locale";

export function middleware(request: NextRequest) {
  const lang = request.nextUrl.searchParams.get("lang");
  if (!isValidLocale(lang)) {
    return NextResponse.next();
  }

  // Request cookie so this render (i18n/request.ts) sees the compose language;
  // response cookie so subsequent navigations keep it.
  request.cookies.set(LOCALE_COOKIE, lang);
  const response = NextResponse.next();
  response.cookies.set(LOCALE_COOKIE, lang, {
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
    sameSite: "lax",
  });
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icons/|logo\\.png|api/).*)"],
};
