"use client";

import { useLocale, useTranslations } from "next-intl";
import type { ReservationStatus } from "@/lib/types";
import { monthLabelForLocale } from "@/lib/locale-format";

const statusKeys: Record<ReservationStatus, string> = {
  expected: "statusExpected",
  checked_in: "statusCheckedIn",
  checked_out: "statusCheckedOut",
  canceled: "statusCanceled",
  pending: "statusPending",
};

export function useReservationStatusLabel() {
  const t = useTranslations("reservation");

  return (status: string): string => {
    const key = statusKeys[status as ReservationStatus];
    return key ? t(key) : status;
  };
}

export {
  reservationStatusClass,
  reservationStatusBarClass,
} from "@/lib/reservationUi";

export { weekdayLabelForLocale } from "@/lib/locale-format";

export function useMonthLabel() {
  const locale = useLocale();
  return (iso: string) => monthLabelForLocale(locale, iso);
}

export { monthLabelForLocale };
