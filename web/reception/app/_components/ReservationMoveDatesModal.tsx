"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ReservationMoveDatesForm } from "@/app/_components/ReservationMoveDatesForm";
import type { ReservationDetail } from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  reservationId: number;
  unitId: number;
  checkIn: string;
  checkOut: string;
  onSuccess: (reservation: ReservationDetail) => void;
};

export function ReservationMoveDatesModal({
  open,
  onClose,
  reservationId,
  unitId,
  checkIn,
  checkOut,
  onSuccess,
}: Props) {
  const t = useTranslations("reservation");
  const tc = useTranslations("common");
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  function handleClose() {
    if (busy) return;
    onClose();
  }

  function handleSuccess(reservation: ReservationDetail) {
    onSuccess(reservation);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        className="card flex w-full max-w-lg flex-col overflow-visible"
        role="dialog"
        aria-modal="true"
        aria-labelledby="move-dates-title"
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 id="move-dates-title" className="font-semibold text-stay-navy">
            {t("moveDates")}
          </h2>
          <button
            type="button"
            className="btn-ghost px-2"
            onClick={handleClose}
            disabled={busy}
            aria-label={tc("close")}
          >
            ×
          </button>
        </div>

        <div className="overflow-visible px-4 py-4 pb-6">
          <ReservationMoveDatesForm
            reservationId={reservationId}
            unitId={unitId}
            checkIn={checkIn}
            checkOut={checkOut}
            onSuccess={handleSuccess}
            onCancel={handleClose}
            onBusyChange={setBusy}
          />
        </div>
      </div>
    </div>
  );
}
