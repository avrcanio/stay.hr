function localeTag(locale: string): string {
  return locale === "hr" ? "hr-HR" : locale === "en" ? "en-GB" : `${locale}-${locale.toUpperCase()}`;
}

export function formatReservationAmount(value: string | number | null | undefined, locale: string): string {
  if (value === null || value === undefined || value === "") return "";
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return String(value);
  return new Intl.NumberFormat(localeTag(locale), {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(num);
}

export function computeNetAmount(
  total: string | null | undefined,
  commission: string | null | undefined,
): number | null {
  if (total == null || total === "" || commission == null || commission === "") return null;
  const totalNum = Number(total);
  const commissionNum = Number(commission);
  if (!Number.isFinite(totalNum) || !Number.isFinite(commissionNum)) return null;
  return totalNum - commissionNum;
}

export function hasFinancialData(reservation: {
  total_amount?: string | null;
  commission_amount?: string | null;
  payment_status?: string;
  booking_payout_received?: boolean;
  booking_payout_received_at?: string | null;
  booking_payout_net?: string | null;
}): boolean {
  return Boolean(
    (reservation.total_amount && reservation.total_amount.trim()) ||
      (reservation.commission_amount && reservation.commission_amount.trim()) ||
      (reservation.payment_status && reservation.payment_status.trim()) ||
      reservation.booking_payout_received ||
      (reservation.booking_payout_received_at && reservation.booking_payout_received_at.trim()) ||
      (reservation.booking_payout_net && reservation.booking_payout_net.trim()),
  );
}
