"use client";

import { useLocale, useTranslations } from "next-intl";
import {
  computeNetAmount,
  formatReservationAmount,
  hasFinancialData,
} from "@/lib/reservationFinance";
import type { ReservationDetail } from "@/lib/types";

type Props = {
  reservation: ReservationDetail;
};

function dash(value: string | null | undefined, fallback: string): string {
  return value && value.trim() ? value.trim() : fallback;
}

export function ReservationFinancialSection({ reservation }: Props) {
  const t = useTranslations("reservation");
  const tc = useTranslations("common");
  const locale = useLocale();
  const dashChar = tc("dash");

  if (!hasFinancialData(reservation)) {
    return (
      <div>
        <h2 className="mb-2 font-semibold">{t("financialTitle")}</h2>
        <p className="text-sm text-muted">{t("financialEmpty")}</p>
      </div>
    );
  }

  const currency = reservation.currency || "EUR";
  const totalFormatted = reservation.total_amount
    ? `${formatReservationAmount(reservation.total_amount, locale)} ${currency}`
    : dashChar;

  const commissionParts: string[] = [];
  if (reservation.commission_amount) {
    commissionParts.push(
      `${formatReservationAmount(reservation.commission_amount, locale)} ${currency}`,
    );
  }
  if (reservation.commission_percent) {
    commissionParts.push(`${formatReservationAmount(reservation.commission_percent, locale)} %`);
  }
  const commissionFormatted = commissionParts.length > 0 ? commissionParts.join(" · ") : dashChar;

  const net = computeNetAmount(reservation.total_amount, reservation.commission_amount);
  const netFormatted =
    net !== null ? `${formatReservationAmount(net, locale)} ${currency}` : dashChar;

  const nightsFormatted =
    reservation.nights_count != null && reservation.nights_count > 0
      ? String(reservation.nights_count)
      : dashChar;

  const payoutReceivedFormatted = reservation.booking_payout_received_at
    ? new Intl.DateTimeFormat(locale === "hr" ? "hr-HR" : "en-GB", {
        dateStyle: "medium",
      }).format(new Date(reservation.booking_payout_received_at))
    : dashChar;

  const payoutNetFormatted = reservation.booking_payout_net
    ? `${formatReservationAmount(reservation.booking_payout_net, locale)} ${currency}`
    : dashChar;

  const payoutServiceFeeFormatted = reservation.booking_payout_service_fee
    ? `${formatReservationAmount(reservation.booking_payout_service_fee, locale)} ${currency}`
    : dashChar;

  const showPayoutSection = Boolean(
    reservation.booking_payout_received ||
      reservation.booking_payout_received_at ||
      reservation.booking_payout_id ||
      reservation.booking_payout_net,
  );

  return (
    <div>
      <h2 className="mb-2 font-semibold">{t("financialTitle")}</h2>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted">{t("financialTotal")}</dt>
          <dd className="font-medium">{totalFormatted}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("financialNights")}</dt>
          <dd className="font-medium">{nightsFormatted}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("financialCommission")}</dt>
          <dd className="font-medium">{commissionFormatted}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("financialNet")}</dt>
          <dd className="font-medium">{netFormatted}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("financialPaymentStatus")}</dt>
          <dd className="font-medium">{dash(reservation.payment_status, dashChar)}</dd>
        </div>
        <div>
          <dt className="text-muted">{t("financialPaymentProvider")}</dt>
          <dd className="font-medium">{dash(reservation.payment_provider, dashChar)}</dd>
        </div>
      </dl>

      {showPayoutSection ? (
        <div className="mt-4 border-t border-border pt-4">
          <h3 className="mb-2 text-sm font-semibold">{t("financialPayoutTitle")}</h3>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted">{t("financialPayoutReceived")}</dt>
              <dd className="font-medium">{payoutReceivedFormatted}</dd>
            </div>
            <div>
              <dt className="text-muted">{t("financialPayoutId")}</dt>
              <dd className="font-medium">{dash(reservation.booking_payout_id, dashChar)}</dd>
            </div>
            <div>
              <dt className="text-muted">{t("financialPayoutNet")}</dt>
              <dd className="font-medium">{payoutNetFormatted}</dd>
            </div>
            {reservation.booking_payout_service_fee ? (
              <div>
                <dt className="text-muted">{t("financialPayoutServiceFee")}</dt>
                <dd className="font-medium">{payoutServiceFeeFormatted}</dd>
              </div>
            ) : null}
          </dl>
        </div>
      ) : null}
    </div>
  );
}
