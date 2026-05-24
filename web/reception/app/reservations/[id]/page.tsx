"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import { ReservationDetailPanel } from "@/app/_components/ReservationDetailPanel";

export default function ReservationDetailPage() {
  const params = useParams<{ id: string }>();
  const t = useTranslations("reservation");
  const [tenantName, setTenantName] = useState("");
  const reservationId = Number(params.id);

  useEffect(() => {
    void fetch("/api/auth/session")
      .then((res) => (res.ok ? res.json() : null))
      .then((s: { tenant?: string } | null) => {
        if (s?.tenant) setTenantName(s.tenant);
      })
      .catch(() => undefined);
  }, []);

  return (
    <div>
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
        <Link href="/" className="text-sm font-medium text-stay-blue hover:underline">
          {t("backToTimeline")}
        </Link>

        {Number.isFinite(reservationId) ? (
          <div className="card space-y-4 p-5">
            <ReservationDetailPanel reservationId={reservationId} />
          </div>
        ) : null}
      </main>
    </div>
  );
}
