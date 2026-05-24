"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { BookingPdfImportForm } from "@/app/_components/BookingPdfImportForm";
import { CountryFlag } from "@/app/_components/CountryFlag";
import { GuestList } from "@/app/_components/GuestList";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import { useImportSourceLabel, useReservationStatusLabel } from "@/lib/i18n-ui";
import { primaryPropertySlug } from "@/lib/app-config";
import { reservationConfirmationPdfPath } from "@/lib/stay-client";
import type { BookingPdfImportResult, ReservationDetail } from "@/lib/types";
import { reservationStatusClass } from "@/lib/reservationUi";

export default function ReservationDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const t = useTranslations("reservation");
  const tc = useTranslations("common");
  const statusLabel = useReservationStatusLabel();
  const importSourceLabel = useImportSourceLabel();
  const [tenantName, setTenantName] = useState("");
  const [propertySlug, setPropertySlug] = useState("");
  const [reservation, setReservation] = useState<ReservationDetail | null>(null);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [canceling, setCanceling] = useState(false);

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
      if (configRes.ok) {
        const config = (await configRes.json()) as {
          tenant?: { slug?: string };
          properties?: Array<{ slug: string }>;
        };
        setPropertySlug(primaryPropertySlug(config));
      }
      const res = await fetch(`/api/stay/reception/reservations/${params.id}/`);
      if (!res.ok) throw new Error(t("notFound"));
      setReservation((await res.json()) as ReservationDetail);
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }, [params.id, t, tc]);

  useEffect(() => {
    void load();
  }, [load]);

  function handleImportSuccess(result: BookingPdfImportResult) {
    if (String(result.id) !== params.id) {
      router.push(`/reservations/${result.id}`);
      return;
    }
    setReservation(result);
    setActionMessage(t("importPdfSuccess"));
  }

  async function handleCancel() {
    if (!reservation || reservation.status !== "expected") return;
    if (!window.confirm(t("cancelConfirm"))) return;

    setCanceling(true);
    setActionMessage("");
    setError("");
    try {
      const res = await fetch(`/api/stay/reception/reservations/${reservation.id}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "canceled" }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as { status?: string[]; detail?: string } | null;
        throw new Error(data?.status?.[0] || data?.detail || t("cancelFailed"));
      }
      setReservation((await res.json()) as ReservationDetail);
      setActionMessage(t("cancelSuccess"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("cancelFailed"));
    } finally {
      setCanceling(false);
    }
  }

  return (
    <div>
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
        <Link href="/" className="text-sm font-medium text-stay-blue hover:underline">
          {t("backToTimeline")}
        </Link>

        {loading ? <p className="text-muted">{tc("loading")}</p> : null}
        {error ? <p className="text-red-600">{error}</p> : null}
        {actionMessage ? <p className="text-sm text-emerald-700">{actionMessage}</p> : null}

        {reservation ? (
          <div className="card space-y-4 p-5">
            <div>
              <h1 className="flex items-center gap-2 text-2xl font-bold text-stay-navy">
                <CountryFlag iso2={reservation.primary_guest_nationality_iso2} size="md" />
                <span>{reservation.primary_guest_name || reservation.room_name}</span>
              </h1>
              <p className="text-muted">
                #{reservation.id} · {reservation.external_id || tc("dash")}
              </p>
            </div>
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted">{t("room")}</dt>
                <dd className="font-medium">{reservation.room_name}</dd>
              </div>
              <div>
                <dt className="text-muted">{t("status")}</dt>
                <dd>
                  <span className={`badge ${reservationStatusClass(reservation.status)}`}>
                    {statusLabel(reservation.status)}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-muted">{t("importSource")}</dt>
                <dd className="font-medium">
                  {importSourceLabel(reservation.import_source, reservation.source)}
                </dd>
              </div>
              <div>
                <dt className="text-muted">{t("checkIn")}</dt>
                <dd className="font-medium">{reservation.check_in_date}</dd>
              </div>
              <div>
                <dt className="text-muted">{t("checkOut")}</dt>
                <dd className="font-medium">{reservation.check_out_date}</dd>
              </div>
              <div>
                <dt className="text-muted">{t("booker")}</dt>
                <dd className="font-medium">{reservation.booker_name || tc("dash")}</dd>
              </div>
              <div>
                <dt className="text-muted">{t("phone")}</dt>
                <dd className="font-medium">{reservation.booker_phone || tc("dash")}</dd>
              </div>
            </dl>

            {reservation.pdf_imported_at || reservation.confirmation_pdf_url ? (
              <p>
                <a
                  href={reservationConfirmationPdfPath(reservation.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-stay-blue hover:underline"
                >
                  {t("downloadPdf")}
                </a>
              </p>
            ) : null}

            {reservation.status === "expected" ? (
              <button type="button" className="btn bg-red-600 text-white hover:bg-red-700" disabled={canceling} onClick={() => void handleCancel()}>
                {t("cancel")}
              </button>
            ) : null}

            <div>
              <h2 className="mb-2 font-semibold">
                {t("guestsTitle", { count: reservation.guests?.length || 0 })}
              </h2>
              <GuestList reservationId={reservation.id} guests={reservation.guests || []} />
            </div>

            {reservation.notes ? (
              <div>
                <h2 className="mb-1 font-semibold">{t("notes")}</h2>
                <p className="whitespace-pre-wrap text-sm text-muted">{reservation.notes}</p>
              </div>
            ) : null}

            <BookingPdfImportForm
              propertySlug={propertySlug}
              reservationId={reservation.id}
              expectedBookingNumber={reservation.external_id || reservation.booking_code}
              onSuccess={handleImportSuccess}
            />

            <p className="text-xs text-stay-muted/70">{t("actionsHint")}</p>
          </div>
        ) : null}
      </main>
    </div>
  );
}
