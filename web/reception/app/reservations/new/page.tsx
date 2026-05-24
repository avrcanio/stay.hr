"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import { UnitAvailabilityDatePicker } from "@/app/_components/UnitAvailabilityDatePicker";
import { singlePropertySlug } from "@/lib/app-config";
import type { AppConfig } from "@/lib/types";
import {
  fetchUnitBlockedNights,
  isCheckInAllowed,
  isCheckOutAllowed,
} from "@/lib/unitAvailability";
import { addDaysIso, addMonthsIso, todayIso } from "@/lib/utils";

export default function NewReservationPage() {
  const router = useRouter();
  const t = useTranslations("newReservation");
  const tc = useTranslations("common");
  const [tenantName, setTenantName] = useState("");
  const [featureFlags, setFeatureFlags] = useState<AppConfig["feature_flags"]>();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [propertySlug, setPropertySlug] = useState("");
  const [unitId, setUnitId] = useState("");
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [bookerName, setBookerName] = useState("");
  const [blockedNights, setBlockedNights] = useState<Set<string>>(new Set());
  const [availabilityLoading, setAvailabilityLoading] = useState(false);

  const today = todayIso();
  const availabilityTo = useMemo(() => addMonthsIso(today, 12), [today]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const session = await fetch("/api/auth/session");
      if (session.ok) {
        const s = await session.json();
        setTenantName(s.tenant || "");
      }

      const configRes = await fetch("/api/stay/app/config");
      if (!configRes.ok) throw new Error(t("loadConfigFailed"));
      const appConfig = (await configRes.json()) as AppConfig;
      setConfig(appConfig);
      setFeatureFlags(appConfig.feature_flags);
      setPropertySlug((current) => current || singlePropertySlug(appConfig));
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }, [t, tc]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!unitId) {
      setBlockedNights(new Set());
      setCheckIn("");
      setCheckOut("");
      return;
    }

    let cancelled = false;
    setAvailabilityLoading(true);
    setCheckIn("");
    setCheckOut("");
    setError("");

    void fetchUnitBlockedNights(Number(unitId), today, availabilityTo)
      .then((nights) => {
        if (!cancelled) setBlockedNights(nights);
      })
      .catch((err) => {
        if (!cancelled) {
          setBlockedNights(new Set());
          setError(err instanceof Error ? err.message : tc("error"));
        }
      })
      .finally(() => {
        if (!cancelled) setAvailabilityLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [unitId, today, availabilityTo, tc]);

  const units = (config?.units ?? []).filter(
    (unit) => !propertySlug || unit.property_slug === propertySlug,
  );
  const properties = config?.properties ?? [];

  const datesValid =
    Boolean(unitId) &&
    Boolean(checkIn) &&
    Boolean(checkOut) &&
    isCheckInAllowed(checkIn, blockedNights, today) &&
    isCheckOutAllowed(checkIn, checkOut, blockedNights);

  function handleCheckInChange(nextCheckIn: string) {
    setCheckIn(nextCheckIn);
    setCheckOut(addDaysIso(nextCheckIn, 1));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!datesValid) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/stay/reception/reservations/create/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          property_slug: propertySlug,
          unit_id: Number(unitId),
          check_in: checkIn,
          check_out: checkOut,
          booker_name: bookerName,
        }),
      });
      const data = (await res.json()) as { id?: number; detail?: string; unit_id?: string[] };
      if (!res.ok) {
        const detail =
          data.detail ||
          (Array.isArray(data.unit_id) ? data.unit_id.join(" ") : undefined) ||
          t("createFailed");
        throw new Error(detail);
      }
      if (data.id) {
        router.push(`/reservations/${data.id}`);
        router.refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("createFailed"));
    } finally {
      setBusy(false);
    }
  }

  if (!loading && featureFlags && !featureFlags.reception_create_reservation) {
    return (
      <div>
        <ReceptionNav tenantName={tenantName} featureFlags={featureFlags} />
        <main className="mx-auto max-w-6xl px-4 py-6">
          <p className="text-muted">{t("notAvailable")}</p>
        </main>
      </div>
    );
  }

  const datesDisabled = !unitId || availabilityLoading;

  return (
    <div>
      <ReceptionNav tenantName={tenantName} featureFlags={featureFlags} />
      <main className="mx-auto max-w-xl space-y-4 px-4 py-6">
        <h1 className="text-xl font-bold text-stay-navy">{t("title")}</h1>
        {loading ? <p className="text-muted">{tc("loading")}</p> : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}

        <form className="card space-y-4 p-4" onSubmit={(e) => void handleSubmit(e)}>
          {properties.length > 1 ? (
            <label className="block text-sm">
              <span className="label">{t("property")}</span>
              <select
                className="input mt-1"
                value={propertySlug}
                onChange={(e) => {
                  setPropertySlug(e.target.value);
                  setUnitId("");
                }}
                required
              >
                <option value="">{t("propertyPlaceholder")}</option>
                {properties.map((property) => (
                  <option key={property.slug} value={property.slug}>
                    {property.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          <label className="block text-sm">
            <span className="label">{t("unit")}</span>
            <select
              className="input mt-1"
              value={unitId}
              onChange={(e) => setUnitId(e.target.value)}
              required
            >
              <option value="">{t("unitPlaceholder")}</option>
              {units.map((unit) => (
                <option key={unit.id} value={unit.id}>
                  {unit.code}
                </option>
              ))}
            </select>
          </label>

          {!unitId ? (
            <p className="text-sm text-muted">{t("selectUnitFirst")}</p>
          ) : availabilityLoading ? (
            <p className="text-sm text-muted">{t("loadingAvailability")}</p>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <UnitAvailabilityDatePicker
              label={t("checkIn")}
              value={checkIn}
              onChange={handleCheckInChange}
              disabled={datesDisabled}
              placeholder={t("selectUnitFirst")}
              isDateDisabled={(iso) => !isCheckInAllowed(iso, blockedNights, today)}
            />
            <UnitAvailabilityDatePicker
              label={t("checkOut")}
              value={checkOut}
              onChange={setCheckOut}
              disabled={datesDisabled || !checkIn}
              placeholder={checkIn ? t("datePlaceholder") : t("selectUnitFirst")}
              anchorDate={checkIn}
              isDateDisabled={(iso) =>
                !checkIn || iso <= checkIn || !isCheckOutAllowed(checkIn, iso, blockedNights)
              }
            />
          </div>

          <label className="block text-sm">
            <span className="label">{t("bookerName")}</span>
            <input
              className="input mt-1"
              value={bookerName}
              onChange={(e) => setBookerName(e.target.value)}
              required
            />
          </label>

          <button
            type="submit"
            className="btn w-full sm:w-auto"
            disabled={busy || datesDisabled || !datesValid}
          >
            {busy ? tc("loading") : t("submit")}
          </button>
        </form>
      </main>
    </div>
  );
}
