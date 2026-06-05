"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { ChannexReview } from "@/lib/types";

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
  const [replyText, setReplyText] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionMessage, setActionMessage] = useState("");

  const baseUrl = `/api/stay/reception/reservations/${reservationId}/reviews`;

  const loadReviews = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${baseUrl}?sync=auto`);
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
  }, [baseUrl, t]);

  useEffect(() => {
    void loadReviews();
  }, [loadReviews]);

  async function handleReply(review: ChannexReview) {
    const text = (replyText[review.id] || "").trim();
    if (!text) return;
    setBusyId(review.id);
    setActionMessage("");
    try {
      const res = await fetch(`/api/stay/reception/reviews/${review.id}/reply/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reply: text }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail || t("replyFailed"));
      }
      setActionMessage(t("replySuccess"));
      await loadReviews();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : t("replyFailed"));
    } finally {
      setBusyId(null);
    }
  }

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
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">{t("title")}</h2>
        {!compact ? (
          <button type="button" className="btn-ghost text-sm" onClick={() => void loadReviews()} disabled={loading}>
            {tc("refresh")}
          </button>
        ) : null}
      </div>

      {reviews.map((review) => (
        <article key={review.id} className="space-y-2 rounded-lg border bg-stay-surface/40 p-3">
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
            {review.is_hidden ? (
              <span className="text-xs text-amber-700">{t("hiddenAirbnb")}</span>
            ) : null}
          </div>

          {review.scores.length > 0 ? (
            <div className="flex flex-wrap gap-2 text-xs text-muted">
              {review.scores.map((score) => (
                <span key={score.category}>
                  {score.category}: {score.score}
                </span>
              ))}
            </div>
          ) : null}

          {review.content ? <p className="whitespace-pre-wrap text-sm">{review.content}</p> : null}

          {review.reply ? (
            <div className="rounded-md border-l-4 border-stay-blue bg-white p-2 text-sm">
              <p className="text-xs font-medium text-muted">{t("yourReply")}</p>
              <p className="whitespace-pre-wrap">{review.reply}</p>
            </div>
          ) : null}

          {review.can_reply ? (
            <div className="space-y-2">
              {review.expired_at ? (
                <p className="text-xs text-muted">
                  {t("replyDeadline", { date: formatReviewTime(review.expired_at) })}
                </p>
              ) : null}
              <textarea
                className="input min-h-[80px] w-full text-sm"
                value={replyText[review.id] || ""}
                onChange={(event) =>
                  setReplyText((prev) => ({ ...prev, [review.id]: event.target.value }))
                }
                placeholder={t("replyPlaceholder")}
                disabled={busyId === review.id}
              />
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => void handleReply(review)}
                disabled={busyId === review.id || !(replyText[review.id] || "").trim()}
              >
                {busyId === review.id ? tc("loading") : t("replyAction")}
              </button>
            </div>
          ) : null}

          {review.can_submit_guest_review ? (
            <p className="text-sm text-amber-800">{t("airbnbGuestReviewHint")}</p>
          ) : null}
        </article>
      ))}

      {actionMessage ? <p className="text-sm text-muted">{actionMessage}</p> : null}

      {compact ? (
        <Link href="/reviews" className="text-sm font-medium text-stay-blue hover:underline">
          {t("openInbox")}
        </Link>
      ) : null}
    </section>
  );
}
