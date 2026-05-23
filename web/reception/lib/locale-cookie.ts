import type { NextResponse } from "next/server";
import { defaultLocale, isValidLocale, LOCALE_COOKIE, type AppLocale } from "@/i18n/locale";

const LOCALE_MAX_AGE = 60 * 60 * 24 * 365;

export function normalizePreferredLocale(value: string | undefined | null): AppLocale {
  if (isValidLocale(value)) {
    return value;
  }
  return defaultLocale;
}

export function applyLocaleCookie(res: NextResponse, locale: AppLocale): void {
  res.cookies.set(LOCALE_COOKIE, locale, {
    path: "/",
    maxAge: LOCALE_MAX_AGE,
    sameSite: "lax",
  });
}

export function readLocaleCookie(cookieValue: string | undefined): AppLocale | null {
  return isValidLocale(cookieValue) ? cookieValue : null;
}
