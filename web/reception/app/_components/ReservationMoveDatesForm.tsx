"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { UnitAvailabilityDatePicker } from "@/app/_components/UnitAvailabilityDatePicker";
import type { ReservationDetail } from "@/lib/types";
import {
  fetchUnitBlockedNights,
  isMoveCheckInAllowed,
  isMoveCheckOutAllowed,
} from "@/lib/unitAvailability";
import { addDaysIso, addMonthsIso, todayIso } from "@/lib/utils";

type Props = {
  reservationId: number;
  unitId: number;
  checkIn: string;
  checkOut: string;
  onSuccess: (reservation: ReservationDetail) => void;
  onCancel: () => void;
  onBusyChange?: (busy: boolean) => void;
};

function parseApiError(data: unknown): string {
  if (!data || typeof data !== "object") return "";
  const record = data as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  for (const key of ["check_in", "check_out", "non_field_errors"]) {
    const value = record[key];
    if (typeof value === "string") return value;
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  }
  return "";
}

export function ReservationMoveDatesForm({
  reservationId,
  unitId,
  checkIn: initialCheckIn,
  checkOut: initialCheckOut,
  onSuccess,
  onCancel,
  onBusyChange,
}: Props) {
  const t = useTranslations("reservation");
  const tc = useTranslations("common");
  const [checkIn, setCheckIn] = useState(initialCheckIn);
  const [checkOut, setCheckOut] = useState(initialCheckOut);
  const [blockedNights, setBlockedNights] = useState<Set<string>>(new Set());
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const today = todayIso();
  const availabilityFrom = initialCheckIn < today ? initialCheckIn : today;
  const availabilityTo = useMemo(() => addMonthsIso(today, 12), [today]);

  useEffect(() => {
    setCheckIn(initialCheckIn);
    setCheckOut(initialCheckOut);
  }, [initialCheckIn, initialCheckOut]);

  useEffect(() => {
    let cancelled = false;
    setAvailabilityLoading(true);
    setError("");

    void fetchUnitBlockedNights(unitId, availabilityFrom, availabilityTo, reservationId)
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
  }, [unitId, reservationId, availabilityFrom, availabilityTo, tc]);

  const datesValid =
    Boolean(checkIn) &&
    Boolean(checkOut) &&
    isMoveCheckInAllowed(checkIn, blockedNights, today, initialCheckIn, initialCheckOut) &&
    isMoveCheckOutAllowed(checkIn, checkOut, blockedNights, initialCheckIn, initialCheckOut);

  const unchanged = checkIn === initialCheckIn && checkOut === initialCheckOut;

  function handleCheckInChange(nextCheckIn: string) {
    setCheckIn(nextCheckIn);
    setCheckOut(addDaysIso(nextCheckIn, 1));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!datesValid || unchanged) return;

    setBusy(true);
    onBusyChange?.(true);
    setError("");
    try {
      const res = await fetch(`/api/stay/reception/reservations/${reservationId}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ check_in: checkIn, check_out: checkOut }),
      });
      const data = (await res.json().catch(() => null)) as unknown;
      if (!res.ok) {
        throw new Error(parseApiError(data) || t("moveDatesFailed"));
      }
      onSuccess(data as ReservationDetail);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("moveDatesFailed"));
    } finally {
      setBusy(false);
      onBusyChange?.(false);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <UnitAvailabilityDatePicker
          label={t("checkIn")}
          value={checkIn}
          onChange={handleCheckInChange}
          disabled={availabilityLoading || busy}
          isDateDisabled={(iso) =>
            !isMoveCheckInAllowed(iso, blockedNights, today, initialCheckIn, initialCheckOut)
          }
        />
        <UnitAvailabilityDatePicker
          label={t("checkOut")}
          value={checkOut}
          onChange={setCheckOut}
          disabled={availabilityLoading || busy || !checkIn}
          anchorDate={checkIn}
          isDateDisabled={(iso) =>
            !isMoveCheckOutAllowed(checkIn, iso, blockedNights, initialCheckIn, initialCheckOut)
          }
        />
      </div>
      {availabilityLoading ? <p className="text-xs text-stay-muted">{tc("loading")}</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn" disabled={busy || !datesValid || unchanged}>
          {busy ? tc("loading") : t("moveDatesSave")}
        </button>
        <button type="button" className="btn-ghost" disabled={busy} onClick={onCancel}>
          {t("moveDatesCancel")}
        </button>
      </div>
    </form>
  );
}
