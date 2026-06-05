"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ReceptionNav } from "@/app/_components/ReceptionNav";
import type { AppConfig, ChannexReview, ChannexReviewsListResponse } from "@/lib/types";

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

export default function ReviewsPage() {
  const t = useTranslations("guestReviews");
  const tc = useTranslations("common");
  const [tenantName, setTenantName] = useState("");
  const [reviews, setReviews] = useState<ChannexReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [unrepliedOnly, setUnrepliedOnly] = useState(true);
  const [selected, setSelected] = useState<ChannexReview | null>(null);
  const [replyText, setReplyText] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState("");

  useEffect(() => {
    void fetch("/api/stay/app/config")
      .then((res) => (res.ok ? res.json() : null))
      .then((config: AppConfig | null) => {
        if (config?.tenant?.name) setTenantName(config.tenant.name);
      })
      .catch(() => undefined);
  }, []);

  const loadReviews = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ sync: "auto", page: "1", page_size: "50" });
      if (unrepliedOnly) params.set("unreplied", "1");
      const res = await fetch(`/api/stay/reception/reviews/?${params.toString()}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail || t("loadFailed"));
      }
      const data = (await res.json()) as ChannexReviewsListResponse;
      setReviews(data.reviews ?? []);
      if (selected) {
        const updated = data.reviews.find((row) => row.id === selected.id);
        if (updated) setSelected(updated);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [selected, t, unrepliedOnly]);

  useEffect(() => {
    void loadReviews();
  }, [loadReviews]);

  async function handleReply() {
    if (!selected) return;
    const text = replyText.trim();
    if (!text) return;
    setBusy(true);
    setActionMessage("");
    try {
      const res = await fetch(`/api/stay/reception/reviews/${selected.id}/reply/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reply: text }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail || t("replyFailed"));
      }
      const updated = (await res.json()) as ChannexReview;
      setSelected(updated);
      setReplyText("");
      setActionMessage(t("replySuccess"));
      await loadReviews();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : t("replyFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-semibold text-stay-navy">{t("inboxTitle")}</h1>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={unrepliedOnly}
                onChange={(event) => setUnrepliedOnly(event.target.checked)}
              />
              {t("filterUnreplied")}
            </label>
            <button type="button" className="btn-ghost btn-sm" onClick={() => void loadReviews()} disabled={loading}>
              {tc("refresh")}
            </button>
          </div>
        </div>

        {error ? <p className="text-sm text-red-600">{error}</p> : null}

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2">
            {loading && reviews.length === 0 ? (
              <p className="text-sm text-muted">{tc("loading")}</p>
            ) : reviews.length === 0 ? (
              <p className="text-sm text-muted">{t("inboxEmpty")}</p>
            ) : (
              reviews.map((review) => (
                <button
                  key={review.id}
                  type="button"
                  onClick={() => {
                    setSelected(review);
                    setReplyText("");
                    setActionMessage("");
                  }}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    selected?.id === review.id ? "border-stay-blue bg-stay-blue-light/30" : "bg-white hover:bg-slate-50"
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-medium">{otaLabel(review.ota)}</span>
                    {review.overall_score != null ? <span>{review.overall_score}/10</span> : null}
                    {!review.is_replied ? (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                        {t("needsReply")}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-muted">
                    {review.content || t("noContentYet")}
                  </p>
                  <p className="mt-1 text-xs text-muted">{formatReviewTime(review.received_at)}</p>
                  {review.reservation_id ? (
                    <Link
                      href={`/reservations/${review.reservation_id}`}
                      className="mt-2 inline-block text-xs font-medium text-stay-blue hover:underline"
                      onClick={(event) => event.stopPropagation()}
                    >
                      {t("openReservation", { code: review.booking_code || review.reservation_id })}
                    </Link>
                  ) : null}
                </button>
              ))
            )}
          </div>

          <div className="rounded-lg border bg-white p-4">
            {!selected ? (
              <p className="text-sm text-muted">{t("selectReview")}</p>
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-stay-navy">{otaLabel(selected.ota)}</span>
                  {selected.overall_score != null ? (
                    <span className="text-lg font-semibold">{selected.overall_score}/10</span>
                  ) : null}
                </div>
                {selected.guest_name ? <p className="text-sm">{selected.guest_name}</p> : null}
                {selected.content ? (
                  <p className="whitespace-pre-wrap text-sm">{selected.content}</p>
                ) : (
                  <p className="text-sm text-muted">{t("noContentYet")}</p>
                )}
                {selected.reply ? (
                  <div className="rounded-md border-l-4 border-stay-blue bg-stay-surface/40 p-2 text-sm">
                    <p className="text-xs font-medium text-muted">{t("yourReply")}</p>
                    <p className="whitespace-pre-wrap">{selected.reply}</p>
                  </div>
                ) : null}
                {selected.can_reply ? (
                  <div className="space-y-2">
                    {selected.expired_at ? (
                      <p className="text-xs text-muted">
                        {t("replyDeadline", { date: formatReviewTime(selected.expired_at) })}
                      </p>
                    ) : null}
                    <textarea
                      className="input min-h-[100px] w-full text-sm"
                      value={replyText}
                      onChange={(event) => setReplyText(event.target.value)}
                      placeholder={t("replyPlaceholder")}
                      disabled={busy}
                    />
                    <button type="button" className="btn btn-sm" onClick={() => void handleReply()} disabled={busy || !replyText.trim()}>
                      {busy ? tc("loading") : t("replyAction")}
                    </button>
                  </div>
                ) : null}
                {selected.can_submit_guest_review ? (
                  <p className="text-sm text-amber-800">{t("airbnbGuestReviewHint")}</p>
                ) : null}
                {actionMessage ? <p className="text-sm text-muted">{actionMessage}</p> : null}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
