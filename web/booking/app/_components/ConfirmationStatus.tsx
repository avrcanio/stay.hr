"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { ReservationStatusResponse } from "@/lib/types";

type Props = {
  bookingCode: string;
  backHref: string;
};

const POLL_MS = 3000;
const MAX_POLLS = 20;

export function ConfirmationStatus({ bookingCode, backHref }: Props) {
  const t = useTranslations("confirmation");
  const [status, setStatus] = useState<ReservationStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let polls = 0;

    async function poll() {
      try {
        const res = await fetch(`/api/booking/status/${encodeURIComponent(bookingCode)}`);
        if (!res.ok) throw new Error(t("lookupFailed"));
        const data = (await res.json()) as ReservationStatusResponse;
        if (cancelled) return;
        setStatus(data);
        setError("");
        setLoading(false);

        if (data.status === "pending" && polls < MAX_POLLS) {
          polls += 1;
          window.setTimeout(() => void poll(), POLL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : t("lookupFailed"));
        setLoading(false);
      }
    }

    void poll();
    return () => {
      cancelled = true;
    };
  }, [bookingCode, t]);

  const resolved = status?.status ?? "pending";
  const title =
    resolved === "expected"
      ? t("titleConfirmed")
      : resolved === "refused"
        ? t("titleRefused")
        : t("titlePending");

  const subtitle =
    resolved === "expected"
      ? t("subtitleConfirmed")
      : resolved === "refused"
        ? t("subtitleRefused")
        : loading
          ? t("subtitlePending")
          : t("subtitlePendingSlow");

  return (
    <div className="card space-y-4 text-center">
      <h1 className="text-2xl font-bold text-stay-blue">{title}</h1>
      <p className="text-muted">{subtitle}</p>
      <p className="text-sm text-muted">{t("codeLabel")}</p>
      <p className="font-mono text-3xl font-bold text-stay-navy">{bookingCode}</p>
      {status ? (
        <p className="text-sm text-muted">
          {status.check_in} → {status.check_out}
          {status.unit_code ? ` · ${status.unit_code}` : ""}
        </p>
      ) : null}
      {loading && resolved === "pending" ? (
        <p className="text-sm text-stay-blue">{t("processing")}</p>
      ) : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <Link href={backHref} className="btn inline-flex">
        {t("backHome")}
      </Link>
    </div>
  );
}
