const PROPERTY_TIME_ZONE = "Europe/Zagreb";

export function todayIso(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: PROPERTY_TIME_ZONE }).format(new Date());
}

export function addDaysIso(iso: string, deltaDays: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + deltaDays);
  return d.toISOString().slice(0, 10);
}

export function startOfMonthIso(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(1);
  return d.toISOString().slice(0, 10);
}

export function addMonthsIso(iso: string, deltaMonths: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() + deltaMonths);
  return d.toISOString().slice(0, 10);
}

export function startOfIsoWeekIso(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  const day = d.getUTCDay();
  const diff = (day + 6) % 7;
  d.setUTCDate(d.getUTCDate() - diff);
  return d.toISOString().slice(0, 10);
}

export function monthLabelHr(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  const raw = new Intl.DateTimeFormat("hr-HR", { month: "long", year: "numeric" }).format(d);
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

export function flagClass(iso2?: string | null): string | null {
  const cc = (iso2 || "").trim().toLowerCase();
  if (!/^[a-z]{2}$/.test(cc)) return null;
  return cc;
}
