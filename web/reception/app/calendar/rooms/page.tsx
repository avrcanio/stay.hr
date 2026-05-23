"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import type { CalendarReservation, Room } from "@/lib/types";
import { addMonthsIso, startOfMonthIso, todayIso } from "@/lib/utils";

export default function RoomCalendarPage() {
  const [tenantName, setTenantName] = useState("");
  const [rooms, setRooms] = useState<Room[]>([]);
  const [month, setMonth] = useState(startOfMonthIso(todayIso()));
  const [byRoom, setByRoom] = useState<Record<number, CalendarReservation[]>>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const session = await fetch("/api/auth/session");
      if (session.ok) {
        const s = await session.json();
        setTenantName(s.tenant || "");
      }
      const roomsRes = await fetch("/api/stay/rooms/rooms/");
      const roomList = (await roomsRes.json()) as Room[];
      setRooms(roomList);

      const to = addMonthsIso(month, 1);
      const entries = await Promise.all(
        roomList.map(async (room) => {
          const res = await fetch(
            `/api/stay/rooms/rooms/${room.id}/calendar/?from=${month}&to=${to}`,
          );
          const data = (await res.json()) as CalendarReservation[];
          return [room.id, data] as const;
        }),
      );
      setByRoom(Object.fromEntries(entries));
    } finally {
      setLoading(false);
    }
  }, [month]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-bold">Kalendar po sobama</h1>
          <input
            type="month"
            className="input w-auto"
            value={month.slice(0, 7)}
            onChange={(e) => setMonth(`${e.target.value}-01`)}
          />
          <button type="button" className="btn" onClick={() => void load()}>
            Osvježi
          </button>
        </div>

        {loading ? <p className="text-stone-500">Učitavanje…</p> : null}

        <div className="space-y-4">
          {rooms.map((room) => (
            <section key={room.id} className="card p-4">
              <h2 className="mb-2 font-semibold">
                {room.code} — {room.room_type_name}
              </h2>
              <ul className="space-y-1 text-sm">
                {(byRoom[room.id] || []).length === 0 ? (
                  <li className="text-stone-500">Nema rezervacija u periodu.</li>
                ) : (
                  (byRoom[room.id] || []).map((r) => (
                    <li key={r.id}>
                      <Link href={`/reservations/${r.id}`} className="text-teal-800 hover:underline">
                        {r.check_in_date} → {r.check_out_date} · {r.primary_guest_name || r.room_name} (
                        {r.status})
                      </Link>
                    </li>
                  ))
                )}
              </ul>
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
