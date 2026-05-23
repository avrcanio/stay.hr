"use client";

import type { CSSProperties } from "react";
import { useLocale, useTranslations } from "next-intl";
import { barSpan, daysInMonth, type CalendarDay } from "@/lib/calendarLayout";
import {
  reservationStatusBarClass,
  useReservationStatusLabel,
  weekdayLabelForLocale,
} from "@/lib/i18n-ui";
import type { CalendarBlock, CalendarReservation, CalendarSelection, Room } from "@/lib/types";
import { standaloneBlocks } from "@/lib/calendarBlocks";
import { todayIso } from "@/lib/utils";

const ROOM_COL_WIDTH = "7.5rem";
const DAY_MIN_WIDTH = "2.25rem";
const ROW_HEIGHT = "2.75rem";

type Props = {
  monthStart: string;
  rooms: Room[];
  byRoom: Record<number, CalendarReservation[]>;
  blocks: CalendarBlock[];
  selection: CalendarSelection | null;
  onSelect: (selection: CalendarSelection) => void;
};

type BarItem =
  | { kind: "reservation"; data: CalendarReservation; zIndex: number }
  | { kind: "block"; data: CalendarBlock; zIndex: number };

function CalendarLegend() {
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
    </div>
  );
}

function DayHeader({ days, today, locale }: { days: CalendarDay[]; today: string; locale: string }) {
  return (
    <>
      <div
        className="sticky left-0 top-0 z-30 border-b border-r border-stay-border bg-white px-2 py-2"
        style={{ width: ROOM_COL_WIDTH, minWidth: ROOM_COL_WIDTH }}
      />
      {days.map((day) => (
        <div
          key={day.iso}
          className={`sticky top-0 z-20 border-b border-stay-border px-0.5 py-1 text-center text-xs ${
            day.iso === today
              ? "bg-stay-blue-light font-semibold text-stay-blue"
              : day.isWeekend
                ? "bg-slate-50 text-stay-muted"
                : "bg-white text-stay-muted"
          }`}
          style={{ minWidth: DAY_MIN_WIDTH }}
        >
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
      <span className="truncate">{guest}</span>
    </button>
  );
}

function RoomRow({
  room,
  days,
  monthStart,
  monthEnd,
  reservations,
  blocks,
  selection,
  today,
  onSelect,
  locale,
}: {
  room: Room;
  days: CalendarDay[];
  monthStart: string;
  monthEnd: string;
  reservations: CalendarReservation[];
  blocks: CalendarBlock[];
  selection: CalendarSelection | null;
  today: string;
  onSelect: (selection: CalendarSelection) => void;
  locale: string;
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

  return (
    <>
      <div
        className="sticky left-0 z-10 flex items-center border-b border-r border-stay-border bg-white px-2 py-2 text-sm font-semibold text-stay-navy"
        style={{ width: ROOM_COL_WIDTH, minWidth: ROOM_COL_WIDTH, height: ROW_HEIGHT }}
        title={`${room.code} — ${room.room_type_name}`}
      >
        <span className="truncate">{room.code}</span>
      </div>

      <div
        className="relative border-b border-stay-border"
        style={{
          display: "grid",
          gridColumn: `2 / -1`,
          gridTemplateColumns: `repeat(${days.length}, minmax(${DAY_MIN_WIDTH}, 1fr))`,
          height: ROW_HEIGHT,
        }}
      >
        {days.map((day) => {
          const selected = selection?.roomId === room.id && selection.date === day.iso;
          return (
            <button
              key={day.iso}
              type="button"
              aria-label={t("roomDayAria", { code: room.code, date: day.iso })}
              className={`border-r border-stay-border last:border-r-0 ${
                day.iso === today ? "bg-stay-blue-light/40" : day.isWeekend ? "bg-slate-50/80" : "bg-white"
              } ${selected ? "ring-2 ring-inset ring-stay-blue" : "hover:bg-stay-blue-light/30"}`}
              onClick={() => onSelect({ roomId: room.id, date: day.iso })}
            />
          );
        })}

        {barItems.map((item) => {
          const range =
            item.kind === "reservation"
              ? { checkIn: item.data.check_in_date, checkOut: item.data.check_out_date }
              : { checkIn: item.data.check_in, checkOut: item.data.check_out };
          const span = barSpan(range.checkIn, range.checkOut, monthStart, monthEnd);
          if (!span) return null;
          const key =
            item.kind === "reservation"
              ? `r-${item.data.id}`
              : `b-${item.data.id ?? item.data.smoobu_booking_id}-${item.data.check_in}`;
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
    </>
  );
}

export function RoomCalendarGrid({
  monthStart,
  rooms,
  byRoom,
  blocks,
  selection,
  onSelect,
}: Props) {
  const locale = useLocale();
  const t = useTranslations("calendar");
  const days = daysInMonth(monthStart);
  const monthEndForSpan =
    days.length > 0
      ? (() => {
          const d = new Date(`${days[days.length - 1].iso}T12:00:00Z`);
          d.setUTCDate(d.getUTCDate() + 1);
          return d.toISOString().slice(0, 10);
        })()
      : monthStart;

  const today = todayIso();
  const gridTemplateColumns = `${ROOM_COL_WIDTH} repeat(${days.length}, minmax(${DAY_MIN_WIDTH}, 1fr))`;

  if (rooms.length === 0) {
    return <p className="text-muted">{t("noActiveRooms")}</p>;
  }

  return (
    <div className="space-y-3">
      <CalendarLegend />
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <div className="min-w-[720px]">
            <div className="grid" style={{ gridTemplateColumns }}>
              <DayHeader days={days} today={today} locale={locale} />
              {rooms.map((room) => (
                <RoomRow
                  key={room.id}
                  room={room}
                  days={days}
                  monthStart={monthStart}
                  monthEnd={monthEndForSpan}
                  reservations={byRoom[room.id] || []}
                  blocks={blocks}
                  selection={selection}
                  today={today}
                  onSelect={onSelect}
                  locale={locale}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
