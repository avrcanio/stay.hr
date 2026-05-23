import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  applyLocaleCookie,
  normalizePreferredLocale,
  readLocaleCookie,
} from "@/lib/locale-cookie";
import { stayFetch } from "@/lib/stay-server";
import { LOCALE_COOKIE } from "@/i18n/locale";

type SessionResponse = {
  ok: boolean;
  user: { username: string; preferred_language: string };
  tenant: { id: number; name: string; slug: string };
};

export async function GET() {
  try {
    const session = await stayFetch<SessionResponse>("/api/v1/auth/reception-session/");
    const preferredLocale = normalizePreferredLocale(session.user.preferred_language);
    const jar = await cookies();
    const currentLocale = readLocaleCookie(jar.get(LOCALE_COOKIE)?.value);
    const localeUpdated = currentLocale !== preferredLocale;

    const res = NextResponse.json({
      ok: true,
      tenant: session.tenant.name,
      localeUpdated,
    });
    if (localeUpdated) {
      applyLocaleCookie(res, preferredLocale);
    }
    return res;
  } catch {
    return NextResponse.json({ ok: false }, { status: 401 });
  }
}
