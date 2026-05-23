"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import type { Reservation, ReservationStatus } from "@/lib/types";
import {
  addDaysIso,
  addMonthsIso,
  monthLabelHr,
  startOfIsoWeekIso,
  startOfMonthIso,
  todayIso,
} from "@/lib/utils";

const statusLabel: Record<ReservationStatus, string> = {
  expected: "Očekuje",
  checked_in: "Prijavljen",
  checked_out: "Odjavljen",
  canceled: "Otkazan",
  pending: "Pending",
};

const statusClass: Record<string, string> = {
  expected: "badge-expected",
  checked_in: "badge-checked_in",
  checked_out: "badge-checked_out",
  canceled: "badge-canceled",
  pending: "badge-expected",
};

type OverviewMode = "today" | "week" | "month" | "all";

export default function TimelinePage() {
  const [tenantName, setTenantName] = useState("");
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [overviewMode, setOverviewMode] = useState<OverviewMode>("today");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const session = await fetch("/api/auth/session");
      if (session.ok) {
        const s = await session.json();
        setTenantName(s.tenant || "");
      }

      const today = todayIso();
      let periodFrom = "";
      let periodTo = "";
      if (overviewMode === "today") {
        periodFrom = today;
        periodTo = addDaysIso(today, 1);
      } else if (overviewMode === "week") {
        periodFrom = startOfIsoWeekIso(today);
        periodTo = addDaysIso(periodFrom, 7);
      } else if (overviewMode === "month") {
        periodFrom = startOfMonthIso(today);
        periodTo = addMonthsIso(periodFrom, 1);
      }

      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (search.trim()) params.set("search", search.trim());
      if (periodFrom) params.set("period_from", periodFrom);
      if (periodTo) params.set("period_to", periodTo);

      const res = await fetch(`/api/stay/reception/reservations/?${params}`);
      if (!res.ok) throw new Error("Učitavanje nije uspjelo");
      const data = (await res.json()) as Reservation[];
      setReservations(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Greška");
    } finally {
      setLoading(false);
    }
  }, [overviewMode, search, status]);

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

  const grouped = useMemo(() => {
    const map = new Map<string, Reservation[]>();
    for (const r of reservations) {
      const key = r.check_in_date;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(r);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [reservations]);

  return (
    <div>
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <div className="text-xs font-semibold uppercase text-stone-500">Period</div>
            <select
              className="input mt-1 w-auto"
              value={overviewMode}
              onChange={(e) => setOverviewMode(e.target.value as OverviewMode)}
            >
              <option value="today">Danas</option>
              <option value="week">Tjedan</option>
              <option value="month">Mjesec</option>
              <option value="all">Sve</option>
            </select>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase text-stone-500">Status</div>
            <select className="input mt-1 w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Svi</option>
              <option value="expected">Očekuje</option>
              <option value="checked_in">Prijavljen</option>
              <option value="checked_out">Odjavljen</option>
              <option value="canceled">Otkazan</option>
            </select>
          </div>
          <div className="min-w-[200px] flex-1">
            <div className="text-xs font-semibold uppercase text-stone-500">Pretraga</div>
            <input
              className="input mt-1"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Ime, soba, ID…"
            />
          </div>
          <button type="button" className="btn" onClick={() => void load()}>
            Osvježi
          </button>
        </div>

        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {loading ? <p className="text-stone-500">Učitavanje…</p> : null}

        {!loading && grouped.length === 0 ? (
          <p className="text-stone-500">Nema rezervacija za odabrane filtere.</p>
        ) : null}

        {grouped.map(([day, items]) => (
          <section key={day} className="space-y-2">
            <h2 className="text-sm font-bold uppercase tracking-wide text-stone-500">
              {monthLabelHr(day)} · dolazak {day}
            </h2>
            <ul className="space-y-2">
              {items.map((r) => (
                <li key={r.id}>
                  <Link
                    href={`/reservations/${r.id}`}
                    className="card flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:border-teal-300"
                  >
                    <div>
                      <div className="font-semibold">{r.primary_guest_name || r.room_name}</div>
                      <div className="text-sm text-stone-500">
                        {r.room_name} · {r.check_in_date} → {r.check_out_date} · {r.guests_count}{" "}
                        gost(a)
                      </div>
                    </div>
                    <span className={`badge ${statusClass[r.status] || "badge-expected"}`}>
                      {statusLabel[r.status] || r.status}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </main>
    </div>
  );
}
