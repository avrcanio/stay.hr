"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import type { ReservationDetail } from "@/lib/types";

export default function ReservationDetailPage() {
  const params = useParams<{ id: string }>();
  const [tenantName, setTenantName] = useState("");
  const [reservation, setReservation] = useState<ReservationDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const session = await fetch("/api/auth/session");
        if (session.ok) {
          const s = await session.json();
          setTenantName(s.tenant || "");
        }
        const res = await fetch(`/api/stay/reception/reservations/${params.id}/`);
        if (!res.ok) throw new Error("Rezervacija nije pronađena");
        setReservation((await res.json()) as ReservationDetail);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Greška");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [params.id]);

  return (
    <div>
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
        <Link href="/" className="text-sm text-teal-700 hover:underline">
          ← Timeline
        </Link>

        {loading ? <p className="text-stone-500">Učitavanje…</p> : null}
        {error ? <p className="text-red-600">{error}</p> : null}

        {reservation ? (
          <div className="card space-y-4 p-5">
            <div>
              <h1 className="text-2xl font-bold">{reservation.primary_guest_name || reservation.room_name}</h1>
              <p className="text-stone-500">
                #{reservation.id} · {reservation.external_id || "—"}
              </p>
            </div>
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-stone-500">Soba</dt>
                <dd className="font-medium">{reservation.room_name}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Status</dt>
                <dd className="font-medium">{reservation.status}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Dolazak</dt>
                <dd className="font-medium">{reservation.check_in_date}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Odlazak</dt>
                <dd className="font-medium">{reservation.check_out_date}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Booker</dt>
                <dd className="font-medium">{reservation.booker_name || "—"}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Telefon</dt>
                <dd className="font-medium">{reservation.booker_phone || "—"}</dd>
              </div>
            </dl>

            <div>
              <h2 className="mb-2 font-semibold">Gosti ({reservation.guests?.length || 0})</h2>
              <ul className="divide-y divide-stone-100 rounded-lg border border-stone-200">
                {(reservation.guests || []).map((g) => (
                  <li key={g.id} className="flex justify-between px-3 py-2 text-sm">
                    <span>
                      {g.first_name} {g.last_name}
                      {g.is_primary ? " · primarni" : ""}
                    </span>
                    <span className="text-stone-500">{g.nationality || "—"}</span>
                  </li>
                ))}
              </ul>
            </div>

            {reservation.notes ? (
              <div>
                <h2 className="mb-1 font-semibold">Napomena</h2>
                <p className="text-sm text-stone-600 whitespace-pre-wrap">{reservation.notes}</p>
              </div>
            ) : null}

            <p className="text-xs text-stone-400">Read-only pregled — izmjene na tabletu (Hospira).</p>
          </div>
        ) : null}
      </main>
    </div>
  );
}
