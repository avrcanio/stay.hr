"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

type Props = {
  action: string;
  propertySlug: string;
  checkIn: string;
  checkOut: string;
};

export function CheckoutForm({ action, propertySlug, checkIn, checkOut }: Props) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      const res = await fetch("/api/booking/reserve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          property_slug: propertySlug,
          check_in: checkIn,
          check_out: checkOut,
          booker_name: form.get("booker_name"),
          booker_email: form.get("booker_email"),
          booker_phone: form.get("booker_phone"),
          guests: [
            {
              first_name: String(form.get("guest_first") || "").trim(),
              last_name: String(form.get("guest_last") || "").trim(),
            },
          ],
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || data.error || "Rezervacija nije uspjela.");
      }
      const base = action.replace(/\/checkout.*$/, "");
      router.push(`${base}/confirmation/${encodeURIComponent(data.booking_code)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Greška");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="card space-y-4">
      <h2 className="text-lg font-semibold">Podaci bookera</h2>
      {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
      <div>
        <label className="label" htmlFor="booker_name">
          Ime i prezime
        </label>
        <input id="booker_name" name="booker_name" className="input mt-1" required />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="booker_email">
            Email
          </label>
          <input id="booker_email" name="booker_email" type="email" className="input mt-1" />
        </div>
        <div>
          <label className="label" htmlFor="booker_phone">
            Telefon
          </label>
          <input id="booker_phone" name="booker_phone" className="input mt-1" />
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="guest_first">
            Ime gosta
          </label>
          <input id="guest_first" name="guest_first" className="input mt-1" required />
        </div>
        <div>
          <label className="label" htmlFor="guest_last">
            Prezime gosta
          </label>
          <input id="guest_last" name="guest_last" className="input mt-1" />
        </div>
      </div>
      <button type="submit" className="btn" disabled={loading}>
        {loading ? "Slanje…" : "Potvrdi rezervaciju"}
      </button>
    </form>
  );
}
