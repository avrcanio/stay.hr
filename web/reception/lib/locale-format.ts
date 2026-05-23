export function monthLabelForLocale(locale: string, iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  const tag =
    locale === "hr" ? "hr-HR" : locale === "en" ? "en-GB" : `${locale}-${locale.toUpperCase()}`;
  const raw = new Intl.DateTimeFormat(tag, { month: "long", year: "numeric" }).format(d);
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

export function weekdayLabelForLocale(locale: string, weekday: number): string {
  const base = new Date(Date.UTC(2024, 0, 7 + weekday));
  const tag =
    locale === "hr" ? "hr-HR" : locale === "en" ? "en-GB" : `${locale}-${locale.toUpperCase()}`;
  return new Intl.DateTimeFormat(tag, { weekday: "short" }).format(base);
}
