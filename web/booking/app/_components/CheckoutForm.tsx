"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { isValidBookerPhone, sanitizePhoneInput } from "@/lib/phoneInput";

type Props = {
  action: string;
  propertySlug: string;
  unitId: number;
  checkIn: string;
  checkOut: string;
};

export function CheckoutForm({ action, propertySlug, unitId, checkIn, checkOut }: Props) {
  const router = useRouter();
  const t = useTranslations("checkout");
  const tc = useTranslations("common");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [bookerPhone, setBookerPhone] = useState("");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const form = new FormData(e.currentTarget);
    const phone = bookerPhone.trim();
    if (phone && !isValidBookerPhone(phone)) {
      setError(t("phoneInvalid"));
      setLoading(false);
      return;
    }
    const firstName = String(form.get("guest_first") || "").trim();
    const lastName = String(form.get("guest_last") || "").trim();
    const bookerName = [firstName, lastName].filter(Boolean).join(" ");

    try {
      const res = await fetch("/api/booking/reserve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          property_slug: propertySlug,
          unit_id: unitId,
          check_in: checkIn,
          check_out: checkOut,
          booker_name: bookerName,
          booker_email: form.get("booker_email"),
          booker_phone: phone,
          guests: [{ first_name: firstName, last_name: lastName }],
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || data.error || t("failed"));
      }
      const base = action.replace(/\/checkout.*$/, "");
      router.push(`${base}/confirmation/${encodeURIComponent(data.booking_code)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="card space-y-4">
      <h2 className="text-lg font-semibold">{t("bookerSection")}</h2>
      {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="guest_first">
            {t("guestFirst")}
          </label>
          <input id="guest_first" name="guest_first" className="input mt-1" required />
        </div>
        <div>
          <label className="label" htmlFor="guest_last">
            {t("guestLast")}
          </label>
          <input id="guest_last" name="guest_last" className="input mt-1" />
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="booker_email">
            {t("email")}
          </label>
          <input id="booker_email" name="booker_email" type="email" className="input mt-1" />
        </div>
        <div>
          <label className="label" htmlFor="booker_phone">
            {t("phone")}
          </label>
          <input
            id="booker_phone"
            name="booker_phone"
            className="input mt-1"
            inputMode="tel"
            autoComplete="tel"
            value={bookerPhone}
            onChange={(event) => setBookerPhone(sanitizePhoneInput(event.target.value))}
            placeholder="+385..."
          />
        </div>
      </div>
      <button type="submit" className="btn" disabled={loading}>
        {loading ? t("submitting") : t("submit")}
      </button>
    </form>
  );
}
