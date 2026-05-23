"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { CountryFlag } from "@/app/_components/CountryFlag";
import { overlapsDay } from "@/lib/calendarLayout";
import { reservationHasChannelBlock, standaloneBlocks } from "@/lib/calendarBlocks";
import { useMonthLabel, useReservationStatusLabel } from "@/lib/i18n-ui";
import { reservationStatusClass } from "@/lib/reservationUi";
import type { CalendarBlock, CalendarReservation, CalendarSelection, Room } from "@/lib/types";

type Props = {
  selection: CalendarSelection | null;
  room: Room | null;
  reservations: CalendarReservation[];
  blocks: CalendarBlock[];
};

export function RoomCalendarDayDetail({ selection, room, reservations, blocks }: Props) {
  const t = useTranslations("calendar");
  const ts = useTranslations("source");
  const statusLabel = useReservationStatusLabel();
  const monthLabel = useMonthLabel();

  if (!selection || !room) {
    return (
      <section className="card p-4">
        <p className="text-sm text-muted">{t("clickDayHint")}</p>
      </section>
    );
  }

  const dayReservations = reservations.filter((r) =>
    overlapsDay(r.check_in_date, r.check_out_date, selection.date),
  );
  const dayBlocks = standaloneBlocks(
    blocks.filter(
      (b) => b.unit_id === room.id && overlapsDay(b.check_in, b.check_out, selection.date),
    ),
  );

  const hasItems = dayReservations.length > 0 || dayBlocks.length > 0;

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold text-stay-navy">
        {room.code} — {room.room_type_name} · {monthLabel(selection.date)} · {selection.date}
      </h2>

      {!hasItems ? (
        <div className="card p-4">
          <p className="text-sm text-muted">{t("noItemsForDay")}</p>
        </div>
      ) : (
        <ul className="space-y-2">
          {dayReservations.map((r) => (
            <li key={`r-${r.id}`}>
              <Link
                href={`/reservations/${r.id}`}
                className="card card-hover flex items-center justify-between gap-3 px-4 py-3"
              >
                <div>
                  <div className="flex items-center gap-2 font-semibold text-stay-navy">
                    <CountryFlag iso2={r.primary_guest_nationality_iso2} />
                    <span>{r.primary_guest_name || r.room_name}</span>
                  </div>
                  <div className="text-sm text-muted">
                    {r.check_in_date} → {r.check_out_date}
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  {reservationHasChannelBlock(r.id, blocks) ? (
                    <span className="badge bg-slate-200 text-slate-800">{t("channelBlocked")}</span>
                  ) : null}
                  <span className={`badge ${reservationStatusClass(r.status)}`}>
                    {statusLabel(r.status)}
                  </span>
                </div>
              </Link>
            </li>
          ))}

          {dayBlocks.map((b) => (
            <li key={`b-${b.id ?? b.smoobu_booking_id}-${b.check_in}`}>
              <div className="card flex flex-wrap items-center justify-between gap-3 border-slate-300 bg-slate-50 px-4 py-3">
                <div>
                  <div className="font-semibold text-stay-navy">{t("blocked")}</div>
                  <div className="text-sm text-muted">
                    {b.check_in} → {b.check_out}
                  </div>
                </div>
                <span className="badge bg-slate-200 text-slate-800">
                  {b.source === "hospira" ? ts("hospira") : ts("smoobu")}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
