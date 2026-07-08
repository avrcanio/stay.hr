"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import { ReportsSubNav } from "@/app/_components/ReportsSubNav";
import { singlePropertySlug } from "@/lib/app-config";
import {
  applyBookingReconcileFixes,
  compareBookingExport,
  fixableFieldKeys,
  recompareBookingExport,
  type BookingReconcileApplyRowResult,
  type BookingReconcileResult,
  type BookingReconcileRow,
} from "@/lib/bookingReconcile";
import { formatReservationAmount } from "@/lib/reservationFinance";
import type { AppConfig } from "@/lib/types";

function SummaryCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-stay-border/60 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-stay-navy">{value}</p>
    </div>
  );
}

export default function BookingReconcilePage() {
  const t = useTranslations("bookingReconcile");
  const tc = useTranslations("common");
  const locale = useLocale();
  const fileRef = useRef<HTMLInputElement>(null);

  const [tenantName, setTenantName] = useState("");
  const [properties, setProperties] = useState<Array<{ slug: string; name: string }>>([]);
  const [propertySlug, setPropertySlug] = useState("");
  const [dateAxis, setDateAxis] = useState<"" | "check_out" | "check_in">("check_out");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [result, setResult] = useState<BookingReconcileResult | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const [applyResults, setApplyResults] = useState<BookingReconcileApplyRowResult[] | null>(null);
  const [lastFile, setLastFile] = useState<File | null>(null);

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
        // surfaced on compare
      }
    })();
  }, []);

  const formatMoney = useCallback(
    (value: string | null | undefined) => {
      if (!value) return tc("dash");
      return `${formatReservationAmount(value, locale)} EUR`;
    },
    [locale, tc],
  );

  const toggleRow = useCallback((row: BookingReconcileRow, checked: boolean) => {
    setSelected((prev) => ({ ...prev, [row.booking_code]: checked }));
  }, []);

  const selectedRows = useMemo(
    () => (result?.rows ?? []).filter((row) => selected[row.booking_code]),
    [result?.rows, selected],
  );

  const runCompare = useCallback(
    async (file: File) => {
      if (!propertySlug) {
        setError(t("errors.propertyRequired"));
        return;
      }
      setLoading(true);
      setError("");
      setApplyResults(null);
      try {
        const payload = await compareBookingExport({
          file,
          propertySlug,
          dateAxis: dateAxis || undefined,
          dateFrom: dateFrom || undefined,
          dateTo: dateTo || undefined,
        });
        setResult(payload);
        setLastFile(file);
        const defaults: Record<string, boolean> = {};
        for (const row of payload.rows) {
          if (row.is_fixable) defaults[row.booking_code] = true;
        }
        setSelected(defaults);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("errors.compareFailed"));
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [propertySlug, dateAxis, dateFrom, dateTo, t],
  );

  const buildApplyItems = useCallback(
    (mode: "fill_empty" | "overwrite") => {
      return selectedRows.map((row) => {
        if (row.match_kind === "missing_in_stay") {
          return { booking_code: row.booking_code, mode };
        }
        return {
          booking_code: row.booking_code,
          fields: fixableFieldKeys(row),
          mode,
        };
      });
    },
    [selectedRows],
  );

  const handleApply = useCallback(
    async (mode: "fill_empty" | "overwrite") => {
      if (!result?.snapshot_id || selectedRows.length === 0) return;
      if (mode === "overwrite") {
        const ok = window.confirm(t("confirmOverwrite"));
        if (!ok) return;
      }
      setApplying(true);
      setError("");
      try {
        const outcome = await applyBookingReconcileFixes({
          snapshotId: result.snapshot_id,
          propertySlug,
          mode,
          confirmOverwrite: mode === "overwrite",
          items: buildApplyItems(mode),
        });
        setApplyResults(outcome.results);
        const priorSnapshotId = result.snapshot_id;
        try {
          const payload = await recompareBookingExport({
            snapshotId: priorSnapshotId,
            propertySlug,
          });
          setResult(payload);
          const defaults: Record<string, boolean> = {};
          for (const row of payload.rows) {
            if (row.is_fixable) defaults[row.booking_code] = true;
          }
          setSelected(defaults);
        } catch {
          if (lastFile) {
            await runCompare(lastFile);
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : t("errors.applyFailed"));
      } finally {
        setApplying(false);
      }
    },
    [result?.snapshot_id, selectedRows, t, propertySlug, buildApplyItems, lastFile, runCompare],
  );

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void runCompare(file);
  }

  return (
    <div className="min-h-screen bg-stay-bg">
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-7xl px-4 py-6">
        <ReportsSubNav />
        <header className="mb-6">
          <h1 className="text-xl font-semibold text-stay-navy">{t("title")}</h1>
          <p className="mt-1 text-sm text-muted">{t("subtitle")}</p>
        </header>

        <section className="card mb-6 space-y-4 p-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <label className="block">
              <div className="label">{t("property")}</div>
              <select
                className="input w-full"
                value={propertySlug}
                onChange={(event) => setPropertySlug(event.target.value)}
              >
                <option value="">{t("propertyPlaceholder")}</option>
                {properties.map((property) => (
                  <option key={property.slug} value={property.slug}>
                    {property.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <div className="label">{t("dateAxis")}</div>
              <select
                className="input w-full"
                value={dateAxis}
                onChange={(event) =>
                  setDateAxis(event.target.value as "" | "check_out" | "check_in")
                }
              >
                <option value="">{t("noPeriodFilter")}</option>
                <option value="check_out">{t("checkOutAxis")}</option>
                <option value="check_in">{t("checkInAxis")}</option>
              </select>
            </label>
            <label className="block">
              <div className="label">{t("dateFrom")}</div>
              <input
                type="date"
                className="input w-full"
                value={dateFrom}
                onChange={(event) => setDateFrom(event.target.value)}
              />
            </label>
            <label className="block">
              <div className="label">{t("dateTo")}</div>
              <input
                type="date"
                className="input w-full"
                value={dateTo}
                onChange={(event) => setDateTo(event.target.value)}
              />
            </label>
          </div>

          <input
            ref={fileRef}
            type="file"
            accept=".xls,application/vnd.ms-excel"
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            type="button"
            className="btn"
            disabled={loading || applying}
            onClick={() => fileRef.current?.click()}
          >
            {loading ? tc("loading") : t("compare")}
          </button>
        </section>

        {error ? <p className="mb-4 text-sm text-red-600">{error}</p> : null}

        {applyResults ? (
          <section className="mb-4 rounded-lg border border-green-200 bg-green-50 p-4 text-sm">
            <h2 className="font-semibold text-stay-navy">{t("applyResultsTitle")}</h2>
            <ul className="mt-2 space-y-1">
              {applyResults.map((row) => (
                <li key={row.booking_code}>
                  {row.booking_code}:{" "}
                  {row.applied ? t("applySuccess") : t("applySkipped", { reason: row.reason })}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {result ? (
          <>
            <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <SummaryCard label={t("summary.matched")} value={result.summary.matched} />
              <SummaryCard
                label={t("summary.differences")}
                value={result.summary.rows_with_differences}
              />
              <SummaryCard label={t("summary.fixable")} value={result.summary.fixable_rows} />
              <SummaryCard
                label={t("summary.missingInStay")}
                value={result.summary.missing_in_stay}
              />
            </section>

            <div className="mb-4 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-sm"
                disabled={applying || selectedRows.length === 0}
                onClick={() => void handleApply("fill_empty")}
              >
                {applying ? tc("loading") : t("applyFillEmpty")}
              </button>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                disabled={applying || selectedRows.length === 0}
                onClick={() => void handleApply("overwrite")}
              >
                {t("applyOverwrite")}
              </button>
            </div>

            <div className="overflow-x-auto rounded-lg border border-stay-border/60 bg-white shadow-sm">
              <table className="min-w-full text-sm">
                <thead className="bg-stay-blue-light/40 text-left">
                  <tr>
                    <th className="px-2 py-2" />
                    <th className="px-2 py-2">{t("columns.booking")}</th>
                    <th className="px-2 py-2">{t("columns.guest")}</th>
                    <th className="px-2 py-2">{t("columns.checkOut")}</th>
                    <th className="px-2 py-2">{t("columns.status")}</th>
                    <th className="px-2 py-2 text-right">{t("columns.gross")}</th>
                    <th className="px-2 py-2 text-right">{t("columns.commission")}</th>
                    <th className="px-2 py-2">{t("columns.diff")}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row) => (
                    <tr
                      key={row.row_key}
                      className={row.has_differences ? "bg-amber-50/70" : undefined}
                    >
                      <td className="px-2 py-2">
                        {row.is_fixable ? (
                          <input
                            type="checkbox"
                            checked={Boolean(selected[row.booking_code])}
                            onChange={(event) => toggleRow(row, event.target.checked)}
                          />
                        ) : null}
                      </td>
                      <td className="px-2 py-2">
                        {row.reservation_id ? (
                          <Link
                            href={`/reservations/${row.reservation_id}`}
                            className="font-medium text-stay-blue hover:underline"
                          >
                            {row.booking_code || tc("dash")}
                          </Link>
                        ) : (
                          row.booking_code || tc("dash")
                        )}
                      </td>
                      <td className="px-2 py-2">{row.guest_name || tc("dash")}</td>
                      <td className="px-2 py-2">{row.check_out || tc("dash")}</td>
                      <td className="px-2 py-2">
                        {row.booking_status || tc("dash")} / {row.stay_status || tc("dash")}
                      </td>
                      <td className="px-2 py-2 text-right">
                        {formatMoney(row.booking_amount)} / {formatMoney(row.stay_amount)}
                      </td>
                      <td className="px-2 py-2 text-right">
                        {formatMoney(row.booking_commission)} / {formatMoney(row.stay_commission)}
                      </td>
                      <td className="px-2 py-2">
                        {row.parse_error ? (
                          <span className="text-red-600">{row.parse_error}</span>
                        ) : row.differences.length ? (
                          <ul className="space-y-1">
                            {row.differences.map((diff) => (
                              <li key={`${row.row_key}-${diff.field_key}`}>
                                <span className="font-medium">{diff.field_label}</span>:{" "}
                                {diff.booking_display} → {diff.stay_display}
                                {diff.block_reasons.length ? (
                                  <span className="text-muted"> ({diff.block_reasons.join(", ")})</span>
                                ) : null}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span className="text-muted">{t("noDiff")}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}
