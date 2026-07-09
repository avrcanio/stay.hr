"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import { ReportsSubNav } from "@/app/_components/ReportsSubNav";
import { singlePropertySlug } from "@/lib/app-config";
import {
  formatDurationSeconds,
  formatPercent,
  guestCheckinReportPath,
  type GuestCheckinReport,
} from "@/lib/guestCheckinReport";
import type { AppConfig } from "@/lib/types";

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-stay-border/60 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-stay-navy">{value}</p>
    </div>
  );
}

export default function GuestCheckinReportPage() {
  const t = useTranslations("guestCheckinReport");
  const tc = useTranslations("common");
  const locale = useLocale();

  const [tenantName, setTenantName] = useState("");
  const [properties, setProperties] = useState<Array<{ slug: string; name: string }>>([]);
  const [propertySlug, setPropertySlug] = useState("");
  const [days, setDays] = useState(30);
  const [report, setReport] = useState<GuestCheckinReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const session = await fetch("/api/auth/session");
        if (session.ok) {
          const data = await session.json();
          setTenantName(data.tenant || "");
        }
        const configRes = await fetch("/api/stay/app/config");
        if (!configRes.ok) return;
        const config = (await configRes.json()) as AppConfig;
        const nextProperties = config.properties ?? [];
        setProperties(nextProperties);
        setPropertySlug((current) => {
          if (current && nextProperties.some((property) => property.slug === current)) {
            return current;
          }
          const single = singlePropertySlug(config);
          if (single) return single;
          return nextProperties[0]?.slug ?? "";
        });
      } catch {
        // bootstrap errors surfaced on load
      }
    })();
  }, []);

  const loadReport = useCallback(async () => {
    if (!propertySlug) {
      setError(t("propertyRequired"));
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await fetch(guestCheckinReportPath({ propertySlug, days }));
      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as { detail?: string; code?: string } | null;
        throw new Error(data?.detail || data?.code || t("loadFailed"));
      }
      setReport((await res.json()) as GuestCheckinReport);
    } catch (err) {
      setReport(null);
      setError(err instanceof Error ? err.message : t("loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [days, propertySlug, t]);

  useEffect(() => {
    if (propertySlug) {
      void loadReport();
    }
  }, [loadReport, propertySlug]);

  const kpis = report?.kpis;
  const reminderChannels = useMemo(() => {
    if (!kpis?.reminders_by_channel) return [];
    return Object.entries(kpis.reminders_by_channel);
  }, [kpis?.reminders_by_channel]);

  const channelLabel = useCallback(
    (channel: string) => {
      if (channel === "email") return t("channelEmail");
      if (channel === "whatsapp") return t("channelWhatsapp");
      if (channel === "booking") return t("channelBooking");
      return t("channelUnknown");
    },
    [t],
  );

  return (
    <div className="min-h-screen bg-stay-bg">
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-6xl px-4 py-6">
        <ReportsSubNav />
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-stay-navy">{t("title")}</h1>
          <p className="mt-1 text-sm text-muted">{t("subtitle")}</p>
        </header>

        <div className="mb-6 flex flex-wrap items-end gap-4 rounded-lg border border-stay-border/60 bg-white p-4">
          <label className="flex min-w-[12rem] flex-col gap-1 text-sm">
            <span className="font-medium text-stay-navy">{t("property")}</span>
            <select
              className="input"
              value={propertySlug}
              onChange={(e) => setPropertySlug(e.target.value)}
            >
              <option value="">{tc("dash")}</option>
              {properties.map((property) => (
                <option key={property.slug} value={property.slug}>
                  {property.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex w-28 flex-col gap-1 text-sm">
            <span className="font-medium text-stay-navy">{t("lookbackDays")}</span>
            <input
              className="input"
              type="number"
              min={1}
              max={365}
              value={days}
              onChange={(e) => setDays(Math.max(1, Number(e.target.value) || 30))}
            />
          </label>
          <button type="button" className="btn" disabled={loading} onClick={() => void loadReport()}>
            {loading ? tc("loading") : t("load")}
          </button>
        </div>

        {error ? <p className="mb-4 text-sm text-red-700">{error}</p> : null}

        {kpis ? (
          <>
            <div className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <KpiCard label={t("kpiCreated")} value={String(kpis.sessions_created)} />
              <KpiCard label={t("kpiActive")} value={String(kpis.sessions_active)} />
              <KpiCard
                label={t("kpiReadyPending")}
                value={String(kpis.sessions_ready_not_completed)}
              />
              <KpiCard label={t("kpiCompleted")} value={String(kpis.sessions_completed)} />
              <KpiCard label={t("kpiExpired")} value={String(kpis.sessions_expired)} />
              <KpiCard
                label={t("kpiCompletionRate")}
                value={formatPercent(kpis.completion_rate, locale)}
              />
              <KpiCard
                label={t("kpiCreatedToReady")}
                value={formatDurationSeconds(kpis.created_to_ready_seconds_median, locale)}
              />
              <KpiCard
                label={t("kpiReadyToComplete")}
                value={formatDurationSeconds(kpis.ready_to_complete_seconds_median, locale)}
              />
              <KpiCard label={t("kpiReminders")} value={String(kpis.reminders_sent)} />
              <KpiCard label={t("kpiOcrApplied")} value={String(kpis.ocr_jobs_applied)} />
              <KpiCard label={t("kpiCompletedOcr")} value={String(kpis.completed_with_ocr)} />
              <KpiCard
                label={t("kpiCompletedManual")}
                value={String(kpis.completed_manual_only)}
              />
            </div>

            {reminderChannels.length > 0 ? (
              <section className="mb-8 rounded-lg border border-stay-border/60 bg-white p-4">
                <h2 className="mb-3 text-sm font-semibold text-stay-navy">
                  {t("remindersByChannel")}
                </h2>
                <ul className="flex flex-wrap gap-4 text-sm text-muted">
                  {reminderChannels.map(([channel, stats]) => (
                    <li key={channel}>
                      <span className="font-medium text-stay-navy">{channelLabel(channel)}</span>:{" "}
                      {stats.sent} {t("reminderSent")} / {stats.total} {t("reminderTotal")}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section className="rounded-lg border border-stay-border/60 bg-white p-4">
              <h2 className="mb-4 text-sm font-semibold text-stay-navy">
                {t("activeSessionsTitle")}
              </h2>
              {report.active_sessions.length === 0 ? (
                <p className="text-sm text-muted">{t("noActiveSessions")}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[48rem] text-left text-sm">
                    <thead>
                      <tr className="border-b border-stay-border/60 text-xs uppercase text-muted">
                        <th className="px-2 py-2">{t("columns.booking")}</th>
                        <th className="px-2 py-2">{t("columns.guest")}</th>
                        <th className="px-2 py-2">{t("columns.checkIn")}</th>
                        <th className="px-2 py-2">{t("columns.progress")}</th>
                        <th className="px-2 py-2">{t("columns.status")}</th>
                        <th className="px-2 py-2">{t("columns.lastActivity")}</th>
                        <th className="px-2 py-2">{t("columns.actions")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.active_sessions.map((row) => {
                        const progressPct =
                          row.progress.required_slots > 0
                            ? Math.round(
                                (row.progress.ready_slots / row.progress.required_slots) * 100,
                              )
                            : 0;
                        const statusLabel =
                          row.effective_status === "ready" ? t("statusReady") : t("statusActive");
                        return (
                          <tr
                            key={row.reservation_id}
                            className="border-b border-stay-border/30 last:border-0"
                          >
                            <td className="px-2 py-3 font-medium">{row.booking_code || "—"}</td>
                            <td className="px-2 py-3">{row.booker_name || "—"}</td>
                            <td className="px-2 py-3">{row.check_in}</td>
                            <td className="px-2 py-3">
                              {row.progress.ready_slots}/{row.progress.required_slots} ({progressPct}
                              %)
                            </td>
                            <td className="px-2 py-3">{statusLabel}</td>
                            <td className="px-2 py-3">
                              {row.last_activity_at
                                ? new Date(row.last_activity_at).toLocaleString(locale)
                                : tc("dash")}
                            </td>
                            <td className="px-2 py-3">
                              <Link
                                href={`/reservations/${row.reservation_id}`}
                                className="text-stay-blue hover:underline"
                              >
                                {t("openReservation")}
                              </Link>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}
