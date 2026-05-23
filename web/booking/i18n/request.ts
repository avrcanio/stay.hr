import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";
import { defaultLocale, isValidLocale, LOCALE_COOKIE, locales } from "./locale";
import { getSiteContext } from "@/lib/site-context";
import { requestHost } from "@/lib/utils";

function localeFromAcceptLanguage(header: string | null): string | undefined {
  if (!header) return undefined;
  for (const part of header.split(",")) {
    const tag = part.split(";")[0]?.trim().toLowerCase();
    if (!tag) continue;
    const primary = tag.split("-")[0];
    if (isValidLocale(tag)) return tag;
    if (isValidLocale(primary)) return primary;
  }
  return undefined;
}

async function siteDefaultLanguage(): Promise<string | undefined> {
  try {
    const host = await requestHost();
    const ctx = await getSiteContext(host);
    const candidate = ctx.default_language || ctx.tenant.default_language;
    return isValidLocale(candidate) ? candidate : undefined;
  } catch {
    return undefined;
  }
}

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get(LOCALE_COOKIE)?.value;
  const headerLocale = localeFromAcceptLanguage((await headers()).get("accept-language"));
  const tenantDefault = await siteDefaultLanguage();

  let locale = defaultLocale;
  if (isValidLocale(cookieLocale)) {
    locale = cookieLocale;
  } else if (isValidLocale(tenantDefault)) {
    locale = tenantDefault;
  } else if (isValidLocale(headerLocale)) {
    locale = headerLocale;
  }

  if (!locales.includes(locale)) {
    locale = defaultLocale;
  }

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
