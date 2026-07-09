"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import type { CheckinProgress, ReservationDetail } from "@/lib/types";
import { useReservationVersionWatch } from "@/lib/useReservationVersionWatch";

type Props = {
  reservationId: number;
  reservationStatus: ReservationDetail["status"];
  progress: CheckinProgress;
  onUpdated: () => void | Promise<void>;
};

export function GuestCheckInProgressSection({
  reservationId,
  reservationStatus,
  progress,
  onUpdated,
}: Props) {
  const t = useTranslations("reservation");
  const tc = useTranslations("common");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const reload = useCallback(() => {
    void onUpdated();
  }, [onUpdated]);

  useReservationVersionWatch({
    reservationId,
    scope: "checkin",
    onVersionChange: reload,
  });

  if (progress.required_slots <= 0 || reservationStatus !== "expected") {
    return null;
  }

  const sessionCompleted = progress.session_status === "completed";
  const hasActiveLink = Boolean(progress.checkin_url);
  const isReady =
    progress.effective_status === "ready" || progress.ready_slots >= progress.required_slots;
  const progressLabel = sessionCompleted
    ? t("checkinProgressCompleted")
    : isReady
      ? t("checkinProgressReady")
      : t("checkinProgress", {
          ready: progress.ready_slots,
          required: progress.required_slots,
        });

  async function copyLink() {
    if (!progress.checkin_url) return;
    try {
      await navigator.clipboard.writeText(progress.checkin_url);
      setMessage(t("checkinLinkCopied"));
    } catch {
      setMessage(tc("error"));
    }
  }

  async function regenerateLink() {
    if (!window.confirm(t("checkinRegenerateConfirm"))) return;
    setBusy(true);
    setMessage("");
    try {
      const res = await fetch(
        `/api/stay/reception/reservations/${reservationId}/guest-checkin/regenerate/`,
        { method: "POST" },
      );
      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail || t("checkinRegenerateFailed"));
      }
      setMessage(t("checkinRegenerateSuccess"));
      await onUpdated();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : tc("error"));
    } finally {
      setBusy(false);
    }
  }

  const barPercent =
    progress.required_slots > 0
      ? Math.round((progress.ready_slots / progress.required_slots) * 100)
      : 0;

  return (
    <div className="rounded-lg border border-stay-border/60 bg-stay-surface/40 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-stay-navy">{t("checkinProgressTitle")}</h2>
        <span className="badge badge-expected text-xs">{progressLabel}</span>
      </div>
      <div
        className="mb-3 h-2 overflow-hidden rounded-full bg-stay-border/40"
        role="progressbar"
        aria-valuenow={progress.ready_slots}
        aria-valuemin={0}
        aria-valuemax={progress.required_slots}
        aria-label={progressLabel}
      >
        <div
          className="h-full rounded-full bg-stay-blue transition-all"
          style={{ width: `${barPercent}%` }}
        />
      </div>
      {!sessionCompleted && progress.waiting_positions.length > 0 ? (
        <p className="mb-3 text-xs text-muted">
          {t("checkinWaitingGuests", {
            positions: progress.waiting_positions.join(", "),
          })}
        </p>
      ) : null}
      {hasActiveLink ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void copyLink()}>
            {t("checkinCopyLink")}
          </button>
          <button
            type="button"
            className="btn btn-sm"
            disabled={busy}
            onClick={() => void regenerateLink()}
          >
            {t("checkinRegenerateLink")}
          </button>
        </div>
      ) : null}
      {message ? <p className="mt-2 text-xs text-emerald-700">{message}</p> : null}
    </div>
  );
}
