"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations, useLocale } from "next-intl";
import type { ChannelRateDay, ObpPolicy, Room } from "@/lib/types";
import {
  channexPushRateFromPolicy,
  computeObpTiersFromPolicy,
  formatObpTierLine,
} from "@/lib/obpPricing";
import { addDaysIso, todayIso } from "@/lib/utils";

export type ChannelRatePlanRow = {
  id: number;
  unit_code: string;
  unit_name: string;
  code: string;
  title: string;
  default_rate: string;
  currency: string;
  obp?: ObpPolicy | null;
};

export type BulkWizardPrefill = {
  roomId?: number;
  dateFrom?: string;
  initialStep?: number;
};

type PushResult = {
  outbox_id?: number;
  kind?: string;
  task_ids?: string[];
  values_count?: number;
};

type ProtectedNightsEntry = {
  unit_code: string;
  dates: string[];
};

type ApplyResponse = {
  rate_days_updated?: number;
  availability_days_updated?: number;
  protected_nights?: ProtectedNightsEntry[];
  push_results?: PushResult[];
  detail?: string;
};

type RestrictionsState = {
  min_stay_arrival: string;
  min_stay_through: string;
  max_stay: string;
  stop_sell: boolean;
  closed_to_arrival: boolean;
  closed_to_departure: boolean;
  showAdvanced: boolean;
};

type Props = {
  open: boolean;
  onClose: () => void;
  onApplied: () => void | Promise<void>;
  rooms: Room[];
  ratePlans: ChannelRatePlanRow[];
  initialUnitId?: number;
  initialDateFrom?: string;
  initialStep?: number;
  channelRatesByUnitDate?: Record<number, Record<string, ChannelRateDay[]>>;
};

const STEPS = 6;

function defaultRestrictions(): RestrictionsState {
  return {
    min_stay_arrival: "1",
    min_stay_through: "",
    max_stay: "",
    stop_sell: false,
    closed_to_arrival: false,
    closed_to_departure: false,
    showAdvanced: false,
  };
}

function ratePrefillForPlan(
  unitId: number | null,
  dateFrom: string,
  planCode: string,
  defaultRate: string,
  channelRatesByUnitDate?: Record<number, Record<string, ChannelRateDay[]>>,
): string {
  if (!unitId || !dateFrom) return defaultRate;
  const rows = channelRatesByUnitDate?.[unitId]?.[dateFrom] ?? [];
  const match = rows.find((r) => r.rate_plan_code === planCode);
  return match?.rate ?? defaultRate;
}

function ratePrefillForSelectedRooms(
  roomIds: number[],
  dateFrom: string,
  planCode: string,
  defaultRate: string,
  channelRatesByUnitDate?: Record<number, Record<string, ChannelRateDay[]>>,
): string {
  for (const roomId of roomIds) {
    const value = ratePrefillForPlan(
      roomId,
      dateFrom,
      planCode,
      defaultRate,
      channelRatesByUnitDate,
    );
    if (value) return value;
  }
  return defaultRate;
}

export function ChannelBulkWizardModal({
  open,
  onClose,
  onApplied,
  rooms,
  ratePlans,
  initialUnitId,
  initialDateFrom,
  initialStep,
  channelRatesByUnitDate,
}: Props) {
  const locale = useLocale();
  const t = useTranslations("calendar.bulkWizard");
  const tc = useTranslations("common");

  const [step, setStep] = useState(1);
  const [unitIds, setUnitIds] = useState<Set<number>>(new Set());
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [rateInputs, setRateInputs] = useState<Record<string, string>>({});
  const [restrictions, setRestrictions] = useState<RestrictionsState>(defaultRestrictions);
  const [availabilityMode, setAvailabilityMode] = useState<"noChange" | "open" | "closed">(
    "noChange",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [applyResult, setApplyResult] = useState<ApplyResponse | null>(null);

  const selectedRooms = useMemo(
    () => rooms.filter((room) => unitIds.has(room.id)),
    [rooms, unitIds],
  );

  const selectedRoomIds = useMemo(() => selectedRooms.map((room) => room.id), [selectedRooms]);

  const sharedRatePlans = useMemo(() => {
    if (selectedRooms.length === 0) return [];
    const selectedCodes = new Set(selectedRooms.map((room) => room.code));
    const byCode = new Map<string, ChannelRatePlanRow>();
    for (const plan of ratePlans) {
      if (!selectedCodes.has(plan.unit_code)) continue;
      if (!byCode.has(plan.code)) byCode.set(plan.code, plan);
    }
    return [...byCode.values()].sort((a, b) => a.code.localeCompare(b.code));
  }, [ratePlans, selectedRooms]);

  useEffect(() => {
    if (!open) return;
    const startStep =
      initialStep != null && initialStep >= 1 && initialStep <= STEPS ? initialStep : 1;
    setStep(startStep);
    setError("");
    setApplyResult(null);
    setRestrictions(defaultRestrictions());
    setAvailabilityMode("noChange");
    const from = initialDateFrom ?? todayIso();
    setDateFrom(from);
    setDateTo(initialDateFrom ? from : addDaysIso(from, 6));
    setUnitIds(initialUnitId != null ? new Set([initialUnitId]) : new Set());
    setRateInputs({});
  }, [open, initialUnitId, initialDateFrom, initialStep]);

  useEffect(() => {
    if (!open || selectedRooms.length === 0 || !dateFrom) return;
    setRateInputs({});
  }, [open, selectedRoomIds.join(","), dateFrom, sharedRatePlans.length]);

  if (!open) return null;

  function toggleRoom(roomId: number) {
    setUnitIds((prev) => {
      const next = new Set(prev);
      if (next.has(roomId)) next.delete(roomId);
      else next.add(roomId);
      return next;
    });
  }

  function selectAllRooms() {
    setUnitIds(new Set(rooms.map((room) => room.id)));
  }

  function clearRoomSelection() {
    setUnitIds(new Set());
  }

  function restrictionsPayload(): Record<string, unknown> {
    const payload: Record<string, unknown> = {};
    const minArrival = restrictions.min_stay_arrival.trim();
    if (minArrival && minArrival !== "1") {
      payload.min_stay_arrival = Number(minArrival);
    }
    const minThrough = restrictions.min_stay_through.trim();
    if (minThrough) payload.min_stay_through = Number(minThrough);
    const maxStay = restrictions.max_stay.trim();
    if (maxStay) payload.max_stay = Number(maxStay);
    if (restrictions.stop_sell) payload.stop_sell = true;
    if (restrictions.closed_to_arrival) payload.closed_to_arrival = true;
    if (restrictions.closed_to_departure) payload.closed_to_departure = true;
    return payload;
  }

  function hasRestrictionOnlyUpdate(): boolean {
    return Object.keys(restrictionsPayload()).length > 0;
  }

  function buildRatesPayload(): Array<Record<string, unknown>> {
    const restrictionFields = restrictionsPayload();
    const items: Array<Record<string, unknown>> = [];

    for (const plan of sharedRatePlans) {
      const rateRaw = (rateInputs[plan.code] ?? "").trim();
      const hasRate = rateRaw.length > 0;
      if (!hasRate && !hasRestrictionOnlyUpdate()) continue;

      const item: Record<string, unknown> = { rate_plan_code: plan.code };
      if (hasRate) item.rate = rateRaw;
      Object.assign(item, restrictionFields);
      if (Object.keys(item).length > 1) items.push(item);
    }
    return items;
  }

  function validateStep(current: number): string | null {
    if (current === 1 && unitIds.size === 0) return t("errors.selectRoom");
    if (current === 2) {
      if (!dateFrom || !dateTo) return t("errors.selectPeriod");
      if (dateTo < dateFrom) return t("errors.periodOrder");
    }
    return null;
  }

  function goNext() {
    const err = validateStep(step);
    if (err) {
      setError(err);
      return;
    }
    setError("");
    setStep((s) => Math.min(STEPS, s + 1));
  }

  function goBack() {
    setError("");
    setStep((s) => Math.max(1, s - 1));
  }

  function goToStep(target: number) {
    if (busy || target < 1 || target > STEPS) return;
    setError("");
    setStep(target);
  }

  async function handleApply() {
    const rates = buildRatesPayload();
    const availability =
      availabilityMode === "noChange" ? null : availabilityMode === "open" ? 1 : 0;
    if (rates.length === 0 && availability === null) {
      setError(t("errors.nothingToApply"));
      return;
    }
    if (selectedRooms.length === 0) {
      setError(t("errors.selectRoom"));
      return;
    }

    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/stay/reception/channel/bulk-apply/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          unit_codes: selectedRooms.map((room) => room.code),
          date_from: dateFrom,
          date_to: dateTo,
          rates,
          availability,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as ApplyResponse;
      if (!res.ok) throw new Error(data.detail || t("errors.applyFailed"));
      setApplyResult(data);
      setStep(STEPS + 1);
      await onApplied();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.applyFailed"));
    } finally {
      setBusy(false);
    }
  }

  function handleClose() {
    if (busy) return;
    onClose();
  }

  const stepTitles = [
    t("steps.room"),
    t("steps.period"),
    t("steps.rates"),
    t("steps.rules"),
    t("steps.availability"),
    t("steps.review"),
  ];

  const reviewRates = buildRatesPayload();
  const reviewAvailability =
    availabilityMode === "noChange"
      ? t("availabilityNoChange")
      : availabilityMode === "open"
        ? t("availabilityOpen")
        : t("availabilityClosed");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        className="card flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bulk-wizard-title"
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 id="bulk-wizard-title" className="font-semibold text-stay-navy">
            {t("title")}
          </h2>
          <button type="button" className="btn-ghost px-2" onClick={handleClose} aria-label={tc("close")}>
            ×
          </button>
        </div>

        {step <= STEPS ? (
          <div className="border-b px-4 py-2">
            <ol className="flex flex-wrap gap-2 text-xs">
              {stepTitles.map((title, i) => {
                const n = i + 1;
                const active = n === step;
                const done = n < step;
                return (
                  <li key={title}>
                    <button
                      type="button"
                      disabled={busy}
                      aria-current={active ? "step" : undefined}
                      aria-label={t("stepNav", { n, title })}
                      className={`rounded-full px-2.5 py-1 transition hover:ring-1 hover:ring-stay-blue/40 disabled:opacity-50 ${
                        active
                          ? "bg-stay-blue text-white"
                          : done
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-slate-100 text-muted"
                      }`}
                      onClick={() => goToStep(n)}
                    >
                      {n}. {title}
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>
        ) : null}

        <div className="flex-1 overflow-y-auto px-4 py-4">
          {step === 1 ? (
            <div className="space-y-3">
              <p className="text-sm text-muted">{t("roomHint")}</p>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn-ghost text-sm" onClick={selectAllRooms}>
                  {t("selectAllRooms")}
                </button>
                {unitIds.size > 0 ? (
                  <button type="button" className="btn-ghost text-sm" onClick={clearRoomSelection}>
                    {t("clearRoomSelection")}
                  </button>
                ) : null}
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {rooms.map((room) => {
                  const selected = unitIds.has(room.id);
                  return (
                    <button
                      key={room.id}
                      type="button"
                      className={`rounded-lg border p-3 text-left ${
                        selected
                          ? "border-stay-blue bg-stay-blue/5 ring-1 ring-stay-blue"
                          : "border-stay-border hover:border-stay-blue/50"
                      }`}
                      onClick={() => toggleRoom(room.id)}
                      aria-pressed={selected}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="font-semibold text-stay-navy">{room.code}</div>
                          <div className="text-sm text-muted">{room.room_type_name}</div>
                        </div>
                        <span
                          className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border text-xs ${
                            selected
                              ? "border-stay-blue bg-stay-blue text-white"
                              : "border-stay-border bg-white text-transparent"
                          }`}
                          aria-hidden
                        >
                          ✓
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
              {unitIds.size > 0 ? (
                <p className="text-sm text-muted">
                  {t("roomsSelected", { count: unitIds.size })}
                </p>
              ) : null}
            </div>
          ) : null}

          {step === 2 ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="label">{t("dateFrom")}</span>
                <input
                  type="date"
                  className="input mt-1"
                  value={dateFrom}
                  onChange={(e) => {
                    const next = e.target.value;
                    setDateFrom(next);
                    if (dateTo && dateTo < next) setDateTo(addDaysIso(next, 1));
                  }}
                />
              </label>
              <label className="block text-sm">
                <span className="label">{t("dateTo")}</span>
                <input
                  type="date"
                  className="input mt-1"
                  value={dateTo}
                  min={dateFrom}
                  onChange={(e) => setDateTo(e.target.value)}
                />
              </label>
            </div>
          ) : null}

          {step === 3 ? (
            <div className="space-y-3">
              <p className="text-sm text-muted">
                {selectedRooms.length > 1 ? t("ratesHintMulti") : t("ratesHint")}
              </p>
              <div className="space-y-4">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[420px] text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted">
                        <th className="py-2 pr-3 font-medium">{t("ratePlan")}</th>
                        <th className="py-2 font-medium">{t("obpBaseRate")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sharedRatePlans.map((plan) => (
                        <tr key={plan.code} className="border-b border-slate-100">
                          <td className="py-2 pr-3">
                            <div className="font-medium">{plan.title || plan.code}</div>
                            <div className="text-xs text-muted">{plan.currency}</div>
                          </td>
                          <td className="py-2">
                            <input
                              className="input w-28"
                              value={rateInputs[plan.code] ?? ""}
                              placeholder={ratePrefillForSelectedRooms(
                                selectedRoomIds,
                                dateFrom,
                                plan.code,
                                plan.default_rate,
                                channelRatesByUnitDate,
                              )}
                              inputMode="decimal"
                              onChange={(e) =>
                                setRateInputs((prev) => ({ ...prev, [plan.code]: e.target.value }))
                              }
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {sharedRatePlans.map((plan) => {
                  const rawRate =
                    rateInputs[plan.code]?.trim() ||
                    ratePrefillForSelectedRooms(
                      selectedRoomIds,
                      dateFrom,
                      plan.code,
                      plan.default_rate,
                      channelRatesByUnitDate,
                    );
                  if (!rawRate.trim()) return null;
                  const unitPlans = ratePlans.filter(
                    (row) =>
                      row.code === plan.code &&
                      selectedRooms.some((room) => room.code === row.unit_code) &&
                      row.obp,
                  );
                  if (unitPlans.length === 0) return null;
                  return (
                    <div key={`${plan.code}-preview`} className="rounded-lg border border-stay-border/70 p-3">
                      <div className="text-sm font-medium text-stay-navy">
                        {plan.title || plan.code} · {t("obpPreview")}
                      </div>
                      <div className="mt-2 space-y-2">
                        {unitPlans.map((unitPlan) => {
                          const tiers = computeObpTiersFromPolicy(rawRate, unitPlan.obp!);
                          const pushRate = channexPushRateFromPolicy(rawRate, unitPlan.obp!);
                          return (
                            <div key={unitPlan.unit_code} className="text-xs text-stay-navy">
                              <div className="font-medium">{unitPlan.unit_code}</div>
                              <div className="text-muted">
                                {tiers.map((tier) => formatObpTierLine(tier, unitPlan.currency, locale)).join(" · ")}
                              </div>
                              {pushRate ? (
                                <div className="text-muted">
                                  {t("obpChannexPushNote", {
                                    rate: pushRate,
                                    occupancy: unitPlan.obp!.primary_occupancy_adults,
                                  })}
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          {step === 4 ? (
            <div className="space-y-3">
              {selectedRooms.length > 1 ? (
                <p className="text-sm text-muted">{t("rulesHintMulti")}</p>
              ) : null}
              <label className="block text-sm">
                <span className="label">{t("minStayArrival")}</span>
                <input
                  type="number"
                  min={1}
                  className="input mt-1 w-24"
                  value={restrictions.min_stay_arrival}
                  onChange={(e) =>
                    setRestrictions((prev) => ({ ...prev, min_stay_arrival: e.target.value }))
                  }
                />
              </label>
              <button
                type="button"
                className="btn-ghost text-sm"
                onClick={() =>
                  setRestrictions((prev) => ({ ...prev, showAdvanced: !prev.showAdvanced }))
                }
              >
                {restrictions.showAdvanced ? t("hideAdvanced") : t("showAdvanced")}
              </button>
              {restrictions.showAdvanced ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block text-sm">
                    <span className="label">{t("minStayThrough")}</span>
                    <input
                      type="number"
                      min={1}
                      className="input mt-1 w-24"
                      value={restrictions.min_stay_through}
                      onChange={(e) =>
                        setRestrictions((prev) => ({ ...prev, min_stay_through: e.target.value }))
                      }
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="label">{t("maxStay")}</span>
                    <input
                      type="number"
                      min={0}
                      className="input mt-1 w-24"
                      value={restrictions.max_stay}
                      onChange={(e) =>
                        setRestrictions((prev) => ({ ...prev, max_stay: e.target.value }))
                      }
                    />
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={restrictions.stop_sell}
                      onChange={(e) =>
                        setRestrictions((prev) => ({ ...prev, stop_sell: e.target.checked }))
                      }
                    />
                    {t("stopSell")}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={restrictions.closed_to_arrival}
                      onChange={(e) =>
                        setRestrictions((prev) => ({
                          ...prev,
                          closed_to_arrival: e.target.checked,
                        }))
                      }
                    />
                    {t("closedToArrival")}
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={restrictions.closed_to_departure}
                      onChange={(e) =>
                        setRestrictions((prev) => ({
                          ...prev,
                          closed_to_departure: e.target.checked,
                        }))
                      }
                    />
                    {t("closedToDeparture")}
                  </label>
                </div>
              ) : null}
            </div>
          ) : null}

          {step === 5 ? (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium text-stay-navy">{t("availabilityTitle")}</legend>
              {selectedRooms.length > 1 ? (
                <p className="text-sm text-muted">{t("availabilityHintMulti")}</p>
              ) : null}
              {(["noChange", "open", "closed"] as const).map((mode) => (
                <label key={mode} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="availabilityMode"
                    checked={availabilityMode === mode}
                    onChange={() => setAvailabilityMode(mode)}
                  />
                  {mode === "noChange"
                    ? t("availabilityNoChange")
                    : mode === "open"
                      ? t("availabilityOpen")
                      : t("availabilityClosed")}
                </label>
              ))}
            </fieldset>
          ) : null}

          {step === 6 ? (
            <dl className="space-y-2 text-sm">
              <div>
                <dt className="text-muted">{t("reviewRooms")}</dt>
                <dd className="font-medium">
                  {selectedRooms.map((room) => room.code).join(", ")}
                </dd>
              </div>
              <div>
                <dt className="text-muted">{t("reviewPeriod")}</dt>
                <dd className="font-medium">
                  {dateFrom} → {dateTo}
                </dd>
              </div>
              <div>
                <dt className="text-muted">{t("reviewRates")}</dt>
                <dd>
                  {reviewRates.length === 0 ? (
                    <span className="text-muted">{t("reviewRatesNone")}</span>
                  ) : (
                    <ul className="mt-1 space-y-1">
                      {reviewRates.map((item) => (
                        <li key={String(item.rate_plan_code)}>
                          <span className="font-medium">{String(item.rate_plan_code)}</span>
                          {item.rate != null ? (
                            <span>
                              {" "}
                              — {String(item.rate)}
                              {item.min_stay_arrival != null
                                ? ` · min ${String(item.min_stay_arrival)}`
                                : ""}
                            </span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-muted">{t("reviewAvailability")}</dt>
                <dd className="font-medium">{reviewAvailability}</dd>
              </div>
            </dl>
          ) : null}

          {step === STEPS + 1 && applyResult ? (
            <div className="space-y-4">
              <p className="text-sm font-medium text-emerald-700">{t("successTitle")}</p>
              <dl className="grid gap-2 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-muted">{t("successRateDays")}</dt>
                  <dd className="font-medium">{applyResult.rate_days_updated ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-muted">{t("successAvailDays")}</dt>
                  <dd className="font-medium">{applyResult.availability_days_updated ?? 0}</dd>
                </div>
              </dl>
              {(applyResult.protected_nights ?? []).length > 0 ? (
                <div className="space-y-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  {(applyResult.protected_nights ?? []).map((entry) => (
                    <p key={entry.unit_code}>
                      {t("protectedNights", {
                        unit: entry.unit_code,
                        count: entry.dates.length,
                        dates: entry.dates.join(", "),
                      })}
                    </p>
                  ))}
                </div>
              ) : null}
              {(applyResult.push_results ?? []).length > 0 ? (
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold text-stay-navy">{t("successTaskIds")}</h3>
                  {(applyResult.push_results ?? []).map((row, i) => (
                    <div key={row.outbox_id ?? i} className="rounded border bg-slate-50 p-2 text-xs">
                      <div className="font-medium">
                        {row.kind ?? t("pushKindUnknown")} · {row.values_count ?? "—"} values
                      </div>
                      <code className="mt-1 block break-all">
                        {(row.task_ids ?? []).join(", ") || tc("dash")}
                      </code>
                    </div>
                  ))}
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn" onClick={handleClose}>
                  {t("viewInCalendar")}
                </button>
              </div>
            </div>
          ) : null}

          {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        </div>

        {step <= STEPS ? (
          <div className="flex justify-between border-t px-4 py-3">
            <button type="button" className="btn-ghost" disabled={step === 1 || busy} onClick={goBack}>
              {t("back")}
            </button>
            {step < STEPS ? (
              <button type="button" className="btn" disabled={busy} onClick={goNext}>
                {t("next")}
              </button>
            ) : (
              <button type="button" className="btn" disabled={busy} onClick={() => void handleApply()}>
                {busy ? tc("loading") : t("apply")}
              </button>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
