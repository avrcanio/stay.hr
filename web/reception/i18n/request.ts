import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";
import { defaultLocale, isValidLocale, LOCALE_COOKIE, locales } from "./locale";

function localeFromAcceptLanguage(header: string | null): string | undefined {
  if (!header) return undefined;
  const parts = header.split(",");
  for (const part of parts) {
    const tag = part.split(";")[0]?.trim().toLowerCase();
    if (!tag) continue;
    const primary = tag.split("-")[0];
    if (isValidLocale(tag)) return tag;
    if (isValidLocale(primary)) return primary;
  }
  return undefined;
}

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get(LOCALE_COOKIE)?.value;
  const headerLocale = localeFromAcceptLanguage((await headers()).get("accept-language"));

  let locale = defaultLocale;
  if (isValidLocale(cookieLocale)) {
    locale = cookieLocale;
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
