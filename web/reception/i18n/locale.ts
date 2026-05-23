export const LOCALE_COOKIE = "stay_locale";

export const locales = ["hr", "en", "es", "fr", "de", "it"] as const;

export type AppLocale = (typeof locales)[number];

export const defaultLocale: AppLocale = "hr";

export const localeLabels: Record<AppLocale, string> = {
  hr: "Hrvatski",
  en: "English",
  es: "Español",
  fr: "Français",
  de: "Deutsch",
  it: "Italiano",
};

export function isValidLocale(value: string | undefined | null): value is AppLocale {
  return locales.includes(value as AppLocale);
}

export function localeToIntlTag(locale: AppLocale): string {
  const map: Record<AppLocale, string> = {
    hr: "hr-HR",
    en: "en-GB",
    es: "es-ES",
    fr: "fr-FR",
    de: "de-DE",
    it: "it-IT",
  };
  return map[locale];
}
