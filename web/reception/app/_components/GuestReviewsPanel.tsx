"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ReviewContentText } from "@/app/_components/ReviewContentText";
import type { ChannexReview } from "@/lib/types";
import { reviewDisplayContent } from "@/lib/review-display";
import { reviewStatusBadges } from "@/lib/review-status-badges";

type Props = {
  reservationId: number;
  compact?: boolean;
};

function formatReviewTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function otaLabel(ota: string): string {
  if (ota === "BookingCom") return "Booking.com";
  if (ota === "AirBNB") return "Airbnb";
  if (ota === "Expedia") return "Expedia";
  return ota || "OTA";
}

export function GuestReviewsPanel({ reservationId, compact = false }: Props) {
  const t = useTranslations("guestReviews");
  const tc = useTranslations("common");
  const [reviews, setReviews] = useState<ChannexReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [displayLang, setDisplayLang] = useState("hr");

  const baseUrl = `/api/stay/reception/reservations/${reservationId}/reviews`;

  const loadReviews = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ sync: "0", lang: displayLang, translate: "1" });
      const res = await fetch(`${baseUrl}?${params.toString()}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail || t("loadFailed"));
      }
      const data = (await res.json()) as { reviews: ChannexReview[] };
      setReviews(data.reviews ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [baseUrl, displayLang, t]);

  useEffect(() => {
    void loadReviews();
  }, [loadReviews]);

  if (loading && reviews.length === 0) {
    return (
      <section className="space-y-2 rounded-lg border p-3">
        <h2 className="font-semibold">{t("title")}</h2>
        <p className="text-sm text-muted">{tc("loading")}</p>
      </section>
    );
  }

  if (error && reviews.length === 0) {
    return (
      <section className="space-y-2 rounded-lg border p-3">
        <h2 className="font-semibold">{t("title")}</h2>
        <p className="text-sm text-red-600">{error}</p>
      </section>
    );
  }

  if (reviews.length === 0) {
    return null;
  }

  return (
    <section className="space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">{t("title")}</h2>
        <div className="flex items-center gap-2">
          {!compact ? (
            <select
              className="input input-sm"
              value={displayLang}
              onChange={(event) => setDisplayLang(event.target.value)}
              aria-label={t("displayLanguage")}
            >
              {["hr", "en", "de", "es", "fr", "it"].map((code) => (
                <option key={code} value={code}>
                  {code.toUpperCase()}
                </option>
              ))}
            </select>
          ) : null}
          {!compact ? (
            <button type="button" className="btn-ghost text-sm" onClick={() => void loadReviews()} disabled={loading}>
              {tc("refresh")}
            </button>
          ) : null}
        </div>
      </div>

      {reviews.map((review) => (
        <Link
          key={review.id}
          href={`/reservations/${reservationId}/reviews/${review.id}`}
          className="block space-y-2 rounded-lg border bg-stay-surface/40 p-3 transition hover:bg-slate-50"
        >
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded-full bg-stay-blue-light px-2 py-0.5 font-medium text-stay-blue">
              {otaLabel(review.ota)}
            </span>
            {review.overall_score != null ? (
              <span className="font-semibold text-stay-navy">{review.overall_score}/10</span>
            ) : null}
            {review.received_at ? (
              <span className="text-muted">{formatReviewTime(review.received_at)}</span>
            ) : null}
            {reviewStatusBadges(review).map((badge) => (
              <span key={badge.key} className={badge.className}>
                {t(badge.key)}
              </span>
            ))}
            {review.is_hidden ? (
              <span className="text-xs text-amber-700">{t("hiddenAirbnb")}</span>
            ) : null}
          </div>

          <p className="line-clamp-2 text-sm text-muted">
            {reviewDisplayContent(review).trim() || t("noContentYet")}
          </p>
        </Link>
      ))}

      {compact ? (
        <Link href="/reviews" className="text-sm font-medium text-stay-blue hover:underline">
          {t("openInbox")}
        </Link>
      ) : null}
    </section>
  );
}
