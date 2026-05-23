"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import { RoomCalendarDayDetail } from "@/app/_components/RoomCalendarDayDetail";
import { RoomCalendarGrid } from "@/app/_components/RoomCalendarGrid";
import { useMonthLabel } from "@/lib/i18n-ui";
import type { CalendarBlock, CalendarReservation, CalendarSelection, Room } from "@/lib/types";
import { addMonthsIso, startOfMonthIso, todayIso } from "@/lib/utils";

function CalendarSkeleton() {
  return (
    <div className="card animate-pulse overflow-hidden p-4">
      <div className="mb-3 h-4 w-48 rounded bg-slate-200" />
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-10 rounded bg-slate-100" />
        ))}
      </div>
    </div>
  );
}

export default function RoomCalendarPage() {
  const t = useTranslations("calendar");
  const tc = useTranslations("common");
  const monthLabel = useMonthLabel();
  const [tenantName, setTenantName] = useState("");
  const [rooms, setRooms] = useState<Room[]>([]);
  const [month, setMonth] = useState(startOfMonthIso(todayIso()));
  const [byRoom, setByRoom] = useState<Record<number, CalendarReservation[]>>({});
  const [blocks, setBlocks] = useState<CalendarBlock[]>([]);
  const [selection, setSelection] = useState<CalendarSelection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const session = await fetch("/api/auth/session");
      if (session.ok) {
        const s = await session.json();
        setTenantName(s.tenant || "");
      }

      const roomsRes = await fetch("/api/stay/rooms/rooms/");
      if (!roomsRes.ok) throw new Error(t("loadRoomsFailed"));
      const roomList = (await roomsRes.json()) as Room[];
      setRooms(roomList);

      const to = addMonthsIso(month, 1);
      const [blockRes, ...roomResults] = await Promise.all([
        fetch(`/api/stay/reception/calendar/blocks/?from=${month}&to=${to}`),
        ...roomList.map(async (room) => {
          const res = await fetch(
            `/api/stay/rooms/rooms/${room.id}/calendar/?from=${month}&to=${to}`,
          );
          if (!res.ok) throw new Error(t("loadRoomFailed", { code: room.code }));
          const data = (await res.json()) as CalendarReservation[];
          return [room.id, data] as const;
        }),
      ]);

      if (!blockRes.ok) throw new Error(t("loadBlocksFailed"));
      const blockList = (await blockRes.json()) as CalendarBlock[];
      setBlocks(blockList);
      setByRoom(Object.fromEntries(roomResults));
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }, [month, t, tc]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => {
      void fetch("/api/stay/reception/sync-versions/")
        .then((r) => {
          if (r.status === 200) void load();
        })
        .catch(() => undefined);
    }, 30000);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    setSelection(null);
  }, [month]);

  const selectedRoom = useMemo(
    () => (selection ? rooms.find((r) => r.id === selection.roomId) ?? null : null),
    [rooms, selection],
  );

  const selectedReservations = selection ? byRoom[selection.roomId] || [] : [];

  function shiftMonth(delta: number) {
    setMonth((current) => addMonthsIso(current, delta));
  }

  return (
    <div>
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-bold">{t("title")}</h1>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="btn-ghost px-2.5"
              aria-label={t("prevMonth")}
              onClick={() => shiftMonth(-1)}
            >
              ‹
            </button>
            <span className="min-w-[9rem] text-center text-sm font-semibold text-stay-navy">
              {monthLabel(month)}
            </span>
            <button
              type="button"
              className="btn-ghost px-2.5"
              aria-label={t("nextMonth")}
              onClick={() => shiftMonth(1)}
            >
              ›
            </button>
          </div>
          <input
            type="month"
            className="input w-auto"
            value={month.slice(0, 7)}
            onChange={(e) => setMonth(`${e.target.value}-01`)}
          />
          <button type="button" className="btn" onClick={() => void load()}>
            {tc("refresh")}
          </button>
        </div>

        {error ? <p className="text-sm text-red-600">{error}</p> : null}

        {loading ? <CalendarSkeleton /> : null}

        {!loading ? (
          <>
            <RoomCalendarGrid
              monthStart={month}
              rooms={rooms}
              byRoom={byRoom}
              blocks={blocks}
              selection={selection}
              onSelect={setSelection}
            />
            <RoomCalendarDayDetail
              selection={selection}
              room={selectedRoom}
              rooms={rooms}
              reservations={selectedReservations}
              byRoom={byRoom}
              blocks={blocks}
              onChanged={load}
            />
          </>
        ) : null}
      </main>
    </div>
  );
}
