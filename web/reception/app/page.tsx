"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { CountryFlag } from "@/app/_components/CountryFlag";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import { useMonthLabel, useReservationStatusLabel } from "@/lib/i18n-ui";
import type { Reservation } from "@/lib/types";
import { reservationStatusClass } from "@/lib/reservationUi";
import {
  addDaysIso,
  addMonthsIso,
  startOfIsoWeekIso,
  startOfMonthIso,
  todayIso,
} from "@/lib/utils";

type OverviewMode = "today" | "week" | "month" | "all";

export default function TimelinePage() {
  const t = useTranslations("timeline");
  const tc = useTranslations("common");
  const tr = useTranslations("reservation");
  const statusLabel = useReservationStatusLabel();
  const monthLabel = useMonthLabel();
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
      if (!res.ok) throw new Error(t("loadFailed"));
      const data = (await res.json()) as Reservation[];
      setReservations(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }, [overviewMode, search, status, t, tc]);

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
            <div className="label">{t("period")}</div>
            <select
              className="input mt-1 w-auto"
              value={overviewMode}
              onChange={(e) => setOverviewMode(e.target.value as OverviewMode)}
            >
              <option value="today">{t("periodToday")}</option>
              <option value="week">{t("periodWeek")}</option>
              <option value="month">{t("periodMonth")}</option>
              <option value="all">{t("periodAll")}</option>
            </select>
          </div>
          <div>
            <div className="label">{t("status")}</div>
            <select className="input mt-1 w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">{t("statusAll")}</option>
              <option value="expected">{tr("statusExpected")}</option>
              <option value="checked_in">{tr("statusCheckedIn")}</option>
              <option value="checked_out">{tr("statusCheckedOut")}</option>
              <option value="canceled">{tr("statusCanceled")}</option>
            </select>
          </div>
          <div className="min-w-[200px] flex-1">
            <div className="label">{t("search")}</div>
            <input
              className="input mt-1"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("searchPlaceholder")}
            />
          </div>
          <button type="button" className="btn" onClick={() => void load()}>
            {tc("refresh")}
          </button>
        </div>

        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {loading ? <p className="text-muted">{tc("loading")}</p> : null}

        {!loading && grouped.length === 0 ? <p className="text-muted">{t("noReservations")}</p> : null}

        {grouped.map(([day, items]) => (
          <section key={day} className="space-y-2">
            <h2 className="label">
              {monthLabel(day)} · {t("arrivalOn", { date: day })}
            </h2>
            <ul className="space-y-2">
              {items.map((r) => (
                <li key={r.id}>
                  <Link
                    href={`/reservations/${r.id}`}
                    className="card card-hover flex flex-wrap items-center justify-between gap-3 px-4 py-3"
                  >
                    <div>
                      <div className="flex items-center gap-2 font-semibold text-stay-navy">
                        <CountryFlag iso2={r.primary_guest_nationality_iso2} />
                        <span>{r.primary_guest_name || r.room_name}</span>
                      </div>
                      <div className="text-sm text-muted">
                        {r.room_name} · {r.check_in_date} → {r.check_out_date} ·{" "}
                        {tc("guestsCount", { count: r.guests_count })}
                      </div>
                    </div>
                    <span className={`badge ${reservationStatusClass(r.status)}`}>
                      {statusLabel(r.status)}
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
