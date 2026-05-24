import type { ChannelAvailabilityDay, ChannelCalendarAri, ChannelRateDay } from "@/lib/types";

function localeTag(locale: string): string {
  return locale === "hr" ? "hr-HR" : locale === "en" ? "en-GB" : `${locale}-${locale.toUpperCase()}`;
}

export function buildChannelAvailabilityMap(
  rows: ChannelAvailabilityDay[],
): Record<number, Record<string, number>> {
  const map: Record<number, Record<string, number>> = {};
  for (const row of rows) {
    if (!map[row.unit_id]) map[row.unit_id] = {};
    map[row.unit_id][row.date] = row.availability;
  }
  return map;
}

export function buildChannelRatesMap(
  rows: ChannelRateDay[],
): Record<number, Record<string, ChannelRateDay[]>> {
  const map: Record<number, Record<string, ChannelRateDay[]>> = {};
  for (const row of rows) {
    if (!map[row.unit_id]) map[row.unit_id] = {};
    if (!map[row.unit_id][row.date]) map[row.unit_id][row.date] = [];
    map[row.unit_id][row.date].push(row);
  }
  return map;
}

export function normalizeChannelCalendarAri(data: ChannelCalendarAri) {
  return {
    availabilityByUnitDate: buildChannelAvailabilityMap(data.availability),
    ratesByUnitDate: buildChannelRatesMap(data.rates),
  };
}

export type RoomRatePlan = {
  code: string;
  title: string;
};

export function ratePlansForRoom(
  roomId: number,
  channelRates?: Record<number, Record<string, ChannelRateDay[]>>,
): RoomRatePlan[] {
  const byDate = channelRates?.[roomId];
  if (!byDate) return [];

  const plans = new Map<string, string>();
  for (const rows of Object.values(byDate)) {
    for (const row of rows) {
      if (!plans.has(row.rate_plan_code)) {
        plans.set(row.rate_plan_code, row.rate_plan_title || row.rate_plan_code);
      }
    }
  }

  return [...plans.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([code, title]) => ({ code, title }));
}

export function formatChannelRateValue(rate: string, locale = "hr"): string {
  const value = Number(rate);
  if (!Number.isFinite(value)) return rate;
  return new Intl.NumberFormat(localeTag(locale), {
    maximumFractionDigits: 0,
    minimumFractionDigits: 0,
  }).format(value);
}

export function rateForPlanOnDate(
  byDate: Record<string, ChannelRateDay[]> | undefined,
  date: string,
  ratePlanCode: string,
): ChannelRateDay | undefined {
  return byDate?.[date]?.find((row) => row.rate_plan_code === ratePlanCode);
}
