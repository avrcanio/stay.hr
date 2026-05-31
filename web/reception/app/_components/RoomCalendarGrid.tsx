"use client";

import type { CSSProperties } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { CountryFlag } from "@/app/_components/CountryFlag";
import { barSpan, daysInRange, ROLLING_WINDOW_DAYS, type CalendarDay } from "@/lib/calendarLayout";
import {
  reservationStatusBarClass,
  useReservationStatusLabel,
  weekdayLabelForLocale,
} from "@/lib/i18n-ui";
import { shortMonthLabelForLocale } from "@/lib/locale-format";
import type { CalendarBlock, CalendarReservation, CalendarSelection, ChannelRateDay, Room } from "@/lib/types";
import { standaloneBlocks } from "@/lib/calendarBlocks";
import {
  formatChannelRateValue,
  rateForPlanOnDate,
  ratePlansForRoom,
  type RoomRatePlan,
} from "@/lib/channelCalendarAri";
import {
  formatObpTierLabel,
  formatObpTierReductionSuffix,
  formatObpTooltip,
  obpAnchorAdultsFromRates,
  obpExpandedTierTemplates,
  obpRateForTier,
  obpTierFromRates,
  obpTierKey,
  type ObpTierTemplate,
} from "@/lib/obpPricing";
import { addDaysIso, todayIso } from "@/lib/utils";

const ROOM_COL_WIDTH = "8.5rem";
const DAY_MIN_WIDTH = "2.25rem";
const ROW_HEIGHT = "2.75rem";
const RATE_ROW_HEIGHT = "1.75rem";

const HIDDEN_SCROLLBAR_CLASS =
  "[scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden";

type Props = {
  rangeStart: string;
  rooms: Room[];
  byRoom: Record<number, CalendarReservation[]>;
  blocks: CalendarBlock[];
  selection: CalendarSelection | null;
  onSelect: (selection: CalendarSelection) => void;
  channelAvailability?: Record<number, Record<string, number>>;
  channelRates?: Record<number, Record<string, ChannelRateDay[]>>;
  showObpTiers?: boolean;
};

type BarItem =
  | { kind: "reservation"; data: CalendarReservation; zIndex: number }
  | { kind: "block"; data: CalendarBlock; zIndex: number };

function daysScrollMinWidth(daysCount: number): string {
  return `calc(${daysCount} * ${DAY_MIN_WIDTH})`;
}

function CalendarLegend({ showChannelAvailability }: { showChannelAvailability: boolean }) {
  const t = useTranslations("calendar");
  const tr = useTranslations("reservation");
  const items = [
    { label: tr("statusExpected"), className: reservationStatusBarClass("expected") },
    { label: tr("statusCheckedIn"), className: reservationStatusBarClass("checked_in") },
    { label: tr("statusCheckedOut"), className: reservationStatusBarClass("checked_out") },
    {
      label: t("block"),
      className: "border border-slate-300 bg-slate-100",
      style: {
        backgroundImage:
          "repeating-linear-gradient(-45deg, transparent, transparent 3px, rgba(148,163,184,0.35) 3px, rgba(148,163,184,0.35) 6px)",
      } as CSSProperties,
    },
  ];

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-stay-muted">
      {items.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          <span
            className={`inline-block h-3 w-5 rounded border ${item.className}`}
            style={item.style}
          />
          {item.label}
        </span>
      ))}
      {showChannelAvailability ? (
        <>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-flex h-3 w-5 items-center justify-center rounded border border-emerald-300 bg-emerald-50 text-[9px] font-semibold text-emerald-700">
              1
            </span>
            {t("channelAvailabilityLegend")}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-flex h-3 w-5 items-center justify-center rounded border border-red-300 bg-red-50 text-[9px] font-semibold text-red-700">
              0
            </span>
            {t("channelSoldOut")}
          </span>
        </>
      ) : null}
      <span className="inline-flex items-center gap-1.5">
        <input
          type="checkbox"
          readOnly
          checked
          tabIndex={-1}
          aria-hidden
          className="pointer-events-none h-3 w-3 rounded border-stay-border"
        />
        {t("syncScroll")}
      </span>
    </div>
  );
}

function DayHeaderCells({
  days,
  today,
  locale,
}: {
  days: CalendarDay[];
  today: string;
  locale: string;
}) {
  return (
    <>
      {days.map((day) => (
        <div
          key={day.iso}
          className={`border-r border-stay-border px-0.5 py-1 text-center text-xs last:border-r-0 ${
            day.iso === today
              ? "bg-stay-blue-light font-semibold text-stay-blue"
              : day.isWeekend
                ? "bg-slate-50 text-stay-muted"
                : "bg-white text-stay-muted"
          }`}
          style={{ minWidth: DAY_MIN_WIDTH }}
        >
          {day.showMonthLabel ? (
            <div className="text-[9px] font-semibold uppercase text-stay-muted">
              {shortMonthLabelForLocale(locale, day.iso)}
            </div>
          ) : null}
          <div className="font-semibold text-stay-navy">{day.dayOfMonth}</div>
          <div className="text-[10px] uppercase">{weekdayLabelForLocale(locale, day.weekday)}</div>
        </div>
      ))}
    </>
  );
}

function CalendarBar({
  item,
  span,
  daysCount,
  onSelect,
  roomId,
}: {
  item: BarItem;
  span: { startCol: number; spanDays: number };
  daysCount: number;
  onSelect: (selection: CalendarSelection) => void;
  roomId: number;
}) {
  const t = useTranslations("calendar");
  const statusLabel = useReservationStatusLabel();

  const leftPct = (span.startCol / daysCount) * 100;
  const widthPct = (span.spanDays / daysCount) * 100;

  if (item.kind === "block") {
    const block = item.data;
    return (
      <button
        type="button"
        title={t("blockTitle", {
          checkIn: block.check_in,
          checkOut: block.check_out,
          source: block.source,
        })}
        className="absolute bottom-1 z-[1] h-5 overflow-hidden rounded border border-slate-300 bg-slate-100 px-1 text-left text-[10px] font-medium leading-5 text-slate-700"
        style={{
          left: `calc(${leftPct}% + 1px)`,
          width: `calc(${widthPct}% - 2px)`,
          backgroundImage:
            "repeating-linear-gradient(-45deg, transparent, transparent 4px, rgba(148,163,184,0.3) 4px, rgba(148,163,184,0.3) 8px)",
          zIndex: item.zIndex,
        }}
        onClick={(e) => {
          e.stopPropagation();
          onSelect({ roomId, date: block.check_in });
        }}
      >
        <span className="truncate">{t("block")}</span>
      </button>
    );
  }

  const reservation = item.data;
  const guest = reservation.primary_guest_name || reservation.room_name;
  const label = statusLabel(reservation.status);

  return (
    <button
      type="button"
      title={`${guest} · ${reservation.check_in_date} → ${reservation.check_out_date} · ${label}`}
      className={`absolute top-1 z-[2] h-5 overflow-hidden rounded border px-1 text-left text-[10px] font-semibold leading-5 ${reservationStatusBarClass(reservation.status)}`}
      style={{
        left: `calc(${leftPct}% + 1px)`,
        width: `calc(${widthPct}% - 2px)`,
        zIndex: item.zIndex,
      }}
      onClick={(e) => {
        e.stopPropagation();
        onSelect({ roomId, date: reservation.check_in_date });
      }}
    >
      <span className="flex min-w-0 items-center gap-0.5">
        <CountryFlag
          iso2={reservation.primary_guest_nationality_iso2}
          className="shrink-0 text-[10px] leading-none"
        />
        <span className="truncate">{guest}</span>
      </span>
    </button>
  );
}

function dayBackgroundClass(day: CalendarDay, today: string): string {
  if (day.iso === today) return "bg-stay-blue-light/40";
  if (day.isWeekend) return "bg-slate-50/80";
  return "bg-white";
}

function RatePlanRow({
  plan,
  days,
  today,
  ratesByDate,
  locale,
  showBaseTierLabel = true,
}: {
  plan: RoomRatePlan;
  days: CalendarDay[];
  today: string;
  ratesByDate?: Record<string, ChannelRateDay[]>;
  locale: string;
  showBaseTierLabel?: boolean;
}) {
  const t = useTranslations("calendar");

  const gridStyle = {
    display: "grid" as const,
    gridTemplateColumns: `repeat(${days.length}, minmax(${DAY_MIN_WIDTH}, 1fr))`,
    minWidth: daysScrollMinWidth(days.length),
    height: RATE_ROW_HEIGHT,
  };

  return (
    <div className="border-t border-stay-border/60" style={gridStyle}>
      {days.map((day) => {
        const rateRow = rateForPlanOnDate(ratesByDate, day.iso, plan.code);
        const formattedRate = rateRow ? formatChannelRateValue(rateRow.rate, locale) : null;
        const obpTooltip =
          rateRow && rateRow.obp_tiers?.length
            ? formatObpTooltip(rateRow.obp_tiers, rateRow.currency, locale, t("obpBaseRate"))
            : null;
        const ariaRate = formattedRate
          ? obpTooltip
            ? `${formattedRate} — ${obpTooltip.replace(/\n/g, "; ")}`
            : formattedRate
          : null;
        return (
          <div
            key={day.iso}
            className={`flex flex-col items-center justify-center border-r border-stay-border px-0.5 text-[9px] font-medium text-stay-navy last:border-r-0 ${dayBackgroundClass(day, today)}`}
            style={{ minWidth: DAY_MIN_WIDTH }}
            title={obpTooltip ?? (formattedRate ? t("channelRateDayAria", { plan: plan.title, date: day.iso, rate: formattedRate }) : undefined)}
            aria-label={
              ariaRate
                ? t("channelRateDayAria", { plan: plan.title, date: day.iso, rate: ariaRate })
                : undefined
            }
          >
            {formattedRate ? (
              <>
                <span className="truncate">{formattedRate}</span>
                {showBaseTierLabel && rateRow?.obp_tiers?.length ? (
                  <span className="truncate text-[8px] font-normal text-stay-muted">
                    {formatObpTierLabel(rateRow.obp_tiers[0], locale)}
                  </span>
                ) : null}
              </>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function ObpTierRow({
  tier,
  plan,
  days,
  today,
  ratesByDate,
  locale,
}: {
  tier: ObpTierTemplate;
  plan: RoomRatePlan;
  days: CalendarDay[];
  today: string;
  ratesByDate?: Record<string, ChannelRateDay[]>;
  locale: string;
}) {
  const t = useTranslations("calendar");
  const tierLabel = formatObpTierLabel({ ...tier, rate: "0" }, locale);
  const sampleRow = days
    .map((day) => rateForPlanOnDate(ratesByDate, day.iso, plan.code))
    .find((row) => row?.obp_tiers?.length);
  const tierData = obpTierFromRates(sampleRow?.obp_tiers, tier.adults, tier.children);
  const reductionSuffix =
    sampleRow && tierData
      ? formatObpTierReductionSuffix(tierData, sampleRow.currency, locale)
      : null;

  const gridStyle = {
    display: "grid" as const,
    gridTemplateColumns: `repeat(${days.length}, minmax(${DAY_MIN_WIDTH}, 1fr))`,
    minWidth: daysScrollMinWidth(days.length),
    height: RATE_ROW_HEIGHT,
  };

  return (
    <div className="border-t border-stay-border/40 bg-slate-50/50" style={gridStyle}>
      {days.map((day) => {
        const rateRow = rateForPlanOnDate(ratesByDate, day.iso, plan.code);
        const rate = obpRateForTier(rateRow?.obp_tiers, tier.adults, tier.children);
        const formattedRate = rate ? formatChannelRateValue(rate, locale) : null;
        return (
          <div
            key={day.iso}
            className={`flex items-center justify-center border-r border-stay-border px-0.5 text-[9px] font-medium text-stay-navy last:border-r-0 ${dayBackgroundClass(day, today)}`}
            style={{ minWidth: DAY_MIN_WIDTH }}
            title={
              formattedRate
                ? t("channelRateDayAria", {
                    plan: `${plan.title} (${tierLabel}${reductionSuffix ? ` ${reductionSuffix}` : ""})`,
                    date: day.iso,
                    rate: formattedRate,
                  })
                : undefined
            }
          >
            {formattedRate ? <span className="truncate">{formattedRate}</span> : null}
          </div>
        );
      })}
    </div>
  );
}

function RatePlanLabelSection({
  plan,
  expanded,
  canExpand,
  onToggle,
  tierTemplates,
  ratesByDate,
  locale,
}: {
  plan: RoomRatePlan;
  expanded: boolean;
  canExpand: boolean;
  onToggle: () => void;
  tierTemplates: ObpTierTemplate[];
  ratesByDate?: Record<string, ChannelRateDay[]>;
  locale: string;
}) {
  const t = useTranslations("calendar");
  const anchorAdults = obpAnchorAdultsFromRates(ratesByDate, plan.code);
  const sampleRow = ratesByDate
    ? Object.values(ratesByDate)
        .flat()
        .find((row) => row.rate_plan_code === plan.code && row.obp_tiers?.length)
    : undefined;
  const labelContent = (
    <>
      {canExpand ? (
        <span className="mr-0.5 shrink-0 text-[8px] leading-none" aria-hidden>
          {expanded ? "▼" : "▶"}
        </span>
      ) : null}
      <span className="truncate">{plan.title}</span>
    </>
  );

  if (!canExpand) {
    return (
      <div
        className="flex items-center truncate border-t border-stay-border/60 pl-5 pr-2 text-[10px] font-medium text-stay-muted"
        style={{ height: RATE_ROW_HEIGHT }}
        title={plan.title}
      >
        {plan.title}
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        className="flex w-full items-center truncate border-t border-stay-border/60 pl-5 pr-2 text-left text-[10px] font-medium text-stay-muted hover:bg-slate-50 hover:text-stay-navy"
        style={{ height: RATE_ROW_HEIGHT }}
        aria-expanded={expanded}
        aria-label={expanded ? t("obpCollapseRates") : t("obpExpandRates")}
        title={plan.title}
        onClick={onToggle}
      >
        {labelContent}
      </button>
      {expanded
        ? tierTemplates.map((tier) => {
            const tierData = obpTierFromRates(sampleRow?.obp_tiers, tier.adults, tier.children);
            const reductionSuffix =
              sampleRow && tierData
                ? formatObpTierReductionSuffix(tierData, sampleRow.currency, locale)
                : null;
            const isNormalTier =
              tier.children === 0 && anchorAdults !== null && tier.adults === anchorAdults;
            return (
            <div
              key={obpTierKey(tier)}
              className="flex items-center truncate border-t border-stay-border/40 bg-slate-50/50 pl-6 pr-2 text-[9px] text-stay-muted"
              style={{ height: RATE_ROW_HEIGHT }}
            >
              {formatObpTierLabel({ ...tier, rate: "0" }, locale)}
              {isNormalTier ? (
                <span className="ml-1 truncate text-[8px]">· {t("obpNormalRate", { occupancy: anchorAdults })}</span>
              ) : reductionSuffix ? (
                <span className="ml-1 truncate text-[8px]">· {reductionSuffix}</span>
              ) : null}
            </div>
            );
          })
        : null}
    </>
  );
}

function RatePlanRatesSection({
  plan,
  days,
  today,
  ratesByDate,
  locale,
  expanded,
  tierTemplates,
  showObpTiers,
}: {
  plan: RoomRatePlan;
  days: CalendarDay[];
  today: string;
  ratesByDate?: Record<string, ChannelRateDay[]>;
  locale: string;
  expanded: boolean;
  tierTemplates: ObpTierTemplate[];
  showObpTiers: boolean;
}) {
  return (
    <>
      <RatePlanRow
        plan={plan}
        days={days}
        today={today}
        ratesByDate={ratesByDate}
        locale={locale}
        showBaseTierLabel={showObpTiers && !expanded}
      />
      {showObpTiers && expanded
        ? tierTemplates.map((tier) => (
            <ObpTierRow
              key={obpTierKey(tier)}
              tier={tier}
              plan={plan}
              days={days}
              today={today}
              ratesByDate={ratesByDate}
              locale={locale}
            />
          ))
        : null}
    </>
  );
}

function RoomRow({
  room,
  days,
  rangeStart,
  rangeEnd,
  reservations,
  blocks,
  selection,
  today,
  onSelect,
  channelAvailability,
  channelRatesByDate,
  ratePlans,
  scrollRef,
  syncEnabled,
  onSyncChange,
  onScroll,
  locale,
  obpExpanded,
  onToggleObp,
  showObpTiers = true,
}: {
  room: Room;
  days: CalendarDay[];
  rangeStart: string;
  rangeEnd: string;
  reservations: CalendarReservation[];
  blocks: CalendarBlock[];
  selection: CalendarSelection | null;
  today: string;
  onSelect: (selection: CalendarSelection) => void;
  channelAvailability?: Record<string, number>;
  channelRatesByDate?: Record<string, ChannelRateDay[]>;
  ratePlans: RoomRatePlan[];
  scrollRef: (node: HTMLDivElement | null) => void;
  syncEnabled: boolean;
  onSyncChange: (enabled: boolean) => void;
  onScroll: (scrollLeft: number) => void;
  locale: string;
  obpExpanded: boolean;
  onToggleObp: () => void;
  showObpTiers: boolean;
}) {
  const t = useTranslations("calendar");
  const roomBlocks = standaloneBlocks(blocks.filter((b) => b.unit_id === room.id));
  const barItems: BarItem[] = [
    ...roomBlocks.map((data, index) => ({ kind: "block" as const, data, zIndex: index + 1 })),
    ...reservations.map((data, index) => ({
      kind: "reservation" as const,
      data,
      zIndex: roomBlocks.length + index + 10,
    })),
  ];

  const dayGridStyle = {
    display: "grid" as const,
    gridTemplateColumns: `repeat(${days.length}, minmax(${DAY_MIN_WIDTH}, 1fr))`,
    minWidth: daysScrollMinWidth(days.length),
    height: ROW_HEIGHT,
  };

  return (
    <div className="flex border-b border-stay-border last:border-b-0">
      <div
        className="flex shrink-0 flex-col border-r border-stay-border bg-white"
        style={{ width: ROOM_COL_WIDTH, minWidth: ROOM_COL_WIDTH }}
      >
        <div
          className="flex items-center gap-1.5 px-2 py-2 text-sm font-semibold text-stay-navy"
          style={{ height: ROW_HEIGHT }}
          title={`${room.code} — ${room.room_type_name}`}
        >
          <input
            type="checkbox"
            checked={syncEnabled}
            onChange={(e) => onSyncChange(e.target.checked)}
            aria-label={t("syncScrollAria", { code: room.code })}
            title={t("syncScroll")}
            className="h-3.5 w-3.5 shrink-0 rounded border-stay-border text-stay-blue focus:ring-stay-blue"
          />
          <span className="truncate">{room.code}</span>
        </div>
        {ratePlans.map((plan) => {
          const tierTemplates = showObpTiers
            ? obpExpandedTierTemplates(channelRatesByDate, plan.code)
            : [];
          const canExpand = showObpTiers && tierTemplates.length > 0;
          const expanded = obpExpanded && canExpand;
          return (
            <RatePlanLabelSection
              key={plan.code}
              plan={plan}
              expanded={expanded}
              canExpand={canExpand}
              onToggle={onToggleObp}
              tierTemplates={tierTemplates}
              ratesByDate={channelRatesByDate}
              locale={locale}
            />
          );
        })}
      </div>

      <div
        ref={scrollRef}
        className={`relative min-w-0 flex-1 overflow-x-auto border-stay-border ${
          syncEnabled ? HIDDEN_SCROLLBAR_CLASS : ""
        }`}
        onScroll={(e) => onScroll(e.currentTarget.scrollLeft)}
      >
        <div className="relative border-stay-border" style={dayGridStyle}>
          {days.map((day) => {
            const selected = selection?.roomId === room.id && selection.date === day.iso;
            const availability = channelAvailability?.[day.iso];
            const availabilityClass =
              availability === 0
                ? "bg-red-50"
                : availability === 1
                  ? "bg-emerald-50/60"
                  : dayBackgroundClass(day, today);
            return (
              <button
                key={day.iso}
                type="button"
                aria-label={t("roomDayAria", { code: room.code, date: day.iso })}
                className={`relative border-r border-stay-border last:border-r-0 ${availabilityClass} ${
                  selected ? "ring-2 ring-inset ring-stay-blue" : "hover:bg-stay-blue-light/30"
                }`}
                onClick={() => onSelect({ roomId: room.id, date: day.iso })}
              >
                {availability !== undefined ? (
                  <span
                    className={`absolute bottom-0.5 right-0.5 rounded px-0.5 text-[9px] font-semibold leading-none ${
                      availability === 0
                        ? "bg-red-100 text-red-700"
                        : "bg-emerald-100 text-emerald-700"
                    }`}
                  >
                    {availability}
                  </span>
                ) : null}
              </button>
            );
          })}

          {barItems.map((item) => {
            const range =
              item.kind === "reservation"
                ? { checkIn: item.data.check_in_date, checkOut: item.data.check_out_date }
                : { checkIn: item.data.check_in, checkOut: item.data.check_out };
            const span = barSpan(range.checkIn, range.checkOut, rangeStart, rangeEnd);
            if (!span) return null;
            const key =
              item.kind === "reservation"
                ? `r-${item.data.id}`
                : `b-${item.data.id ?? item.data.block_ref}-${item.data.check_in}`;
            return (
              <CalendarBar
                key={key}
                item={item}
                span={span}
                daysCount={days.length}
                onSelect={onSelect}
                roomId={room.id}
              />
            );
          })}
        </div>

        {ratePlans.map((plan) => {
          const tierTemplates = showObpTiers
            ? obpExpandedTierTemplates(channelRatesByDate, plan.code)
            : [];
          const expanded = showObpTiers && obpExpanded && tierTemplates.length > 0;
          return (
            <RatePlanRatesSection
              key={plan.code}
              plan={plan}
              days={days}
              today={today}
              ratesByDate={channelRatesByDate}
              locale={locale}
              expanded={expanded}
              tierTemplates={tierTemplates}
              showObpTiers={showObpTiers}
            />
          );
        })}
      </div>
    </div>
  );
}

export function RoomCalendarGrid({
  rangeStart,
  rooms,
  byRoom,
  blocks,
  selection,
  onSelect,
  channelAvailability,
  channelRates,
  showObpTiers = true,
}: Props) {
  const locale = useLocale();
  const t = useTranslations("calendar");
  const days = daysInRange(rangeStart, ROLLING_WINDOW_DAYS);
  const rangeEnd = addDaysIso(rangeStart, ROLLING_WINDOW_DAYS);

  const today = todayIso();
  const syncingRef = useRef(false);
  const headerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Record<number, HTMLDivElement | null>>({});

  const [syncByRoom, setSyncByRoom] = useState<Record<number, boolean>>(() =>
    Object.fromEntries(rooms.map((room) => [room.id, true])),
  );
  const [obpExpandedByRoom, setObpExpandedByRoom] = useState<Record<number, boolean>>({});

  useEffect(() => {
    setSyncByRoom((prev) => {
      const next = { ...prev };
      for (const room of rooms) {
        if (!(room.id in next)) {
          next[room.id] = true;
        }
      }
      for (const roomId of Object.keys(next)) {
        if (!rooms.some((room) => room.id === Number(roomId))) {
          delete next[Number(roomId)];
        }
      }
      return next;
    });
  }, [rooms]);

  useEffect(() => {
    headerRef.current?.scrollTo({ left: 0 });
    for (const room of rooms) {
      rowRefs.current[room.id]?.scrollTo({ left: 0 });
    }
  }, [rangeStart, rooms]);

  const propagateScroll = useCallback(
    (source: "header" | number, scrollLeft: number) => {
      if (syncingRef.current) return;
      syncingRef.current = true;

      if (source !== "header" && headerRef.current) {
        headerRef.current.scrollLeft = scrollLeft;
      }

      for (const room of rooms) {
        if (syncByRoom[room.id] && source !== room.id) {
          const rowEl = rowRefs.current[room.id];
          if (rowEl) {
            rowEl.scrollLeft = scrollLeft;
          }
        }
      }

      requestAnimationFrame(() => {
        syncingRef.current = false;
      });
    },
    [rooms, syncByRoom],
  );

  const handleHeaderScroll = useCallback(
    (scrollLeft: number) => {
      propagateScroll("header", scrollLeft);
    },
    [propagateScroll],
  );

  const handleRowScroll = useCallback(
    (roomId: number, scrollLeft: number) => {
      if (!syncByRoom[roomId]) return;
      propagateScroll(roomId, scrollLeft);
    },
    [propagateScroll, syncByRoom],
  );

  const handleSyncChange = useCallback((roomId: number, enabled: boolean) => {
    setSyncByRoom((prev) => ({ ...prev, [roomId]: enabled }));
    if (enabled) {
      const syncScrollLeft = headerRef.current?.scrollLeft ?? 0;
      requestAnimationFrame(() => {
        const rowEl = rowRefs.current[roomId];
        if (rowEl) {
          rowEl.scrollLeft = syncScrollLeft;
        }
      });
    }
  }, []);

  const toggleObpExpanded = useCallback((roomId: number) => {
    setObpExpandedByRoom((prev) => ({ ...prev, [roomId]: !prev[roomId] }));
  }, []);

  const setRowRef = useCallback((roomId: number) => {
    return (node: HTMLDivElement | null) => {
      rowRefs.current[roomId] = node;
    };
  }, []);

  if (rooms.length === 0) {
    return <p className="text-muted">{t("noActiveRooms")}</p>;
  }

  const headerGridStyle = {
    display: "grid" as const,
    gridTemplateColumns: `repeat(${days.length}, minmax(${DAY_MIN_WIDTH}, 1fr))`,
    minWidth: daysScrollMinWidth(days.length),
  };

  return (
    <div className="space-y-3">
      <CalendarLegend showChannelAvailability={Boolean(channelAvailability)} />
      <div className="card overflow-hidden">
        <div className="flex border-b border-stay-border">
          <div
            className="shrink-0 border-r border-stay-border bg-white px-2 py-2"
            style={{ width: ROOM_COL_WIDTH, minWidth: ROOM_COL_WIDTH }}
          />
          <div
            ref={headerRef}
            className="min-w-0 flex-1 overflow-x-auto"
            onScroll={(e) => handleHeaderScroll(e.currentTarget.scrollLeft)}
          >
            <div style={headerGridStyle}>
              <DayHeaderCells days={days} today={today} locale={locale} />
            </div>
          </div>
        </div>

        {rooms.map((room) => (
          <RoomRow
            key={room.id}
            room={room}
            days={days}
            rangeStart={rangeStart}
            rangeEnd={rangeEnd}
            reservations={byRoom[room.id] || []}
            blocks={blocks}
            selection={selection}
            today={today}
            onSelect={onSelect}
            channelAvailability={channelAvailability?.[room.id]}
            channelRatesByDate={channelRates?.[room.id]}
            ratePlans={ratePlansForRoom(room.id, channelRates)}
            scrollRef={setRowRef(room.id)}
            syncEnabled={syncByRoom[room.id] ?? true}
            onSyncChange={(enabled) => handleSyncChange(room.id, enabled)}
            onScroll={(scrollLeft) => handleRowScroll(room.id, scrollLeft)}
            locale={locale}
            obpExpanded={obpExpandedByRoom[room.id] ?? false}
            onToggleObp={() => toggleObpExpanded(room.id)}
            showObpTiers={showObpTiers}
          />
        ))}
      </div>
    </div>
  );
}
