"use client";

import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { LOCALE_COOKIE, localeLabels, locales, type AppLocale } from "@/i18n/locale";

type Props = {
  languages?: string[];
};

export function LanguageSwitcher({ languages }: Props) {
  const locale = useLocale() as AppLocale;
  const router = useRouter();
  const t = useTranslations("language");

  const availableLocales = (languages?.filter((code): code is AppLocale => locales.includes(code as AppLocale)) ??
    locales) as AppLocale[];

  const options = availableLocales.length > 0 ? availableLocales : locales;

  function onChange(nextLocale: string) {
    if (!locales.includes(nextLocale as AppLocale)) return;
    document.cookie = `${LOCALE_COOKIE}=${nextLocale};path=/;max-age=31536000;SameSite=Lax`;
    router.refresh();
  }

  return (
    <label className="inline-flex items-center gap-1.5 text-sm">
      <span className="sr-only">{t("label")}</span>
      <select
        className="input w-auto py-1.5 text-sm"
        value={locale}
        onChange={(e) => onChange(e.target.value)}
        aria-label={t("label")}
      >
        {options.map((code) => (
          <option key={code} value={code}>
            {localeLabels[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
