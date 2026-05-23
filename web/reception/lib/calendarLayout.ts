import { addDaysIso, addMonthsIso } from "@/lib/utils";

export type BarSpan = {
  startCol: number;
  spanDays: number;
};

export type CalendarDay = {
  iso: string;
  dayOfMonth: number;
  weekday: number;
  isWeekend: boolean;
};

function compareIso(a: string, b: string): number {
  return a.localeCompare(b);
}

export function maxDate(a: string, b: string): string {
  return compareIso(a, b) >= 0 ? a : b;
}

export function minDate(a: string, b: string): string {
  return compareIso(a, b) <= 0 ? a : b;
}

export function daysBetween(fromIso: string, toIso: string): number {
  const from = new Date(`${fromIso}T12:00:00Z`);
  const to = new Date(`${toIso}T12:00:00Z`);
  return Math.round((to.getTime() - from.getTime()) / 86_400_000);
}

export function monthEndExclusive(monthStart: string): string {
  return addMonthsIso(monthStart, 1);
}

export function daysInMonth(monthStart: string): CalendarDay[] {
  const end = monthEndExclusive(monthStart);
  const days: CalendarDay[] = [];
  let cursor = monthStart;
  while (cursor < end) {
    const d = new Date(`${cursor}T12:00:00Z`);
    const weekday = d.getUTCDay();
    days.push({
      iso: cursor,
      dayOfMonth: d.getUTCDate(),
      weekday,
      isWeekend: weekday === 0 || weekday === 6,
    });
    cursor = addDaysIso(cursor, 1);
  }
  return days;
}

export function barSpan(
  checkIn: string,
  checkOut: string,
  monthStart: string,
  monthEnd: string,
): BarSpan | null {
  if (checkOut <= monthStart || checkIn >= monthEnd) return null;
  const start = maxDate(checkIn, monthStart);
  const end = minDate(checkOut, monthEnd);
  const startCol = daysBetween(monthStart, start);
  const spanDays = daysBetween(start, end);
  if (spanDays <= 0) return null;
  return { startCol, spanDays };
}

export function overlapsDay(checkIn: string, checkOut: string, dayIso: string): boolean {
  const nextDay = addDaysIso(dayIso, 1);
  return checkIn < nextDay && checkOut > dayIso;
}

export function weekdayLabelHr(weekday: number): string {
  const labels = ["Ned", "Pon", "Uto", "Sri", "Čet", "Pet", "Sub"];
  return labels[weekday] || "";
}
