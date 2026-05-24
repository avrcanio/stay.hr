import { addDaysIso } from "@/lib/utils";

function localeTag(locale: string): string {
  return locale === "hr" ? "hr-HR" : locale === "en" ? "en-GB" : `${locale}-${locale.toUpperCase()}`;
}

export function monthLabelForLocale(locale: string, iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  const raw = new Intl.DateTimeFormat(localeTag(locale), { month: "long", year: "numeric" }).format(d);
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

export function shortMonthLabelForLocale(locale: string, iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return new Intl.DateTimeFormat(localeTag(locale), { month: "short" }).format(d).toUpperCase();
}

export function shortDateLabelForLocale(
  locale: string,
  iso: string,
  includeYear = false,
): string {
  const d = new Date(`${iso}T12:00:00Z`);
  const options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" };
  if (includeYear) {
    options.year = "numeric";
  }
  return new Intl.DateTimeFormat(localeTag(locale), options).format(d);
}

export function formatDateRangeLabel(
  locale: string,
  fromIso: string,
  toExclusiveIso: string,
): string {
  const lastDayIso = addDaysIso(toExclusiveIso, -1);
  const fromYear = fromIso.slice(0, 4);
  const toYear = lastDayIso.slice(0, 4);
  const fromPart = shortDateLabelForLocale(locale, fromIso, fromYear !== toYear);
  const toPart = shortDateLabelForLocale(locale, lastDayIso, true);
  return `${fromPart} – ${toPart}`;
}

export function weekdayLabelForLocale(locale: string, weekday: number): string {
  const base = new Date(Date.UTC(2024, 0, 7 + weekday));
  return new Intl.DateTimeFormat(localeTag(locale), { weekday: "short" }).format(base);
}
