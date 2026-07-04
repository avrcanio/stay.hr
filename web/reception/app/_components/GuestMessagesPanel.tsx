"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import type {
  GuestMessageChannelInfo,
  GuestMessageChannels,
  GuestMessageComposeResponse,
  GuestMessageTimelineItem,
} from "@/lib/types";

type Props = {
  reservationId: number;
};

type ComposeIntent = "checkin" | "reply" | "custom";

const CHANNEL_ORDER = ["email", "whatsapp", "booking"] as const;

function formatMessageTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function channelLabelKey(channel: string): string {
  if (channel === "booking") return "channelBooking";
  if (channel === "whatsapp") return "channelWhatsapp";
  return "channelEmail";
}

function timelineChannelLabels(
  item: GuestMessageTimelineItem,
  t: (key: string) => string,
): string {
  const channels = item.channels?.length ? item.channels : [item.channel];
  return channels.map((channel) => t(channelLabelKey(channel))).join(" · ");
}

function channelHint(
  channel: string,
  channels: GuestMessageChannels,
  t: (key: string, values?: Record<string, string>) => string,
): string | null {
  if (channel === "booking" && channels.booking?.available) {
    return t("channelBookingHint");
  }
  if (channel === "email" && channels.email?.available && channels.email.to) {
    return t("channelEmailHint", { email: channels.email.to });
  }
  if (channel === "whatsapp" && channels.whatsapp?.available) {
    if (channels.whatsapp.api_send) {
      return t("channelWhatsappApiHint");
    }
    const phone = channels.whatsapp.phone_raw || channels.whatsapp.phone_wa || "";
    if (phone) {
      return t("channelWhatsappHint", { phone });
    }
  }
  return null;
}

export function GuestMessagesPanel({ reservationId }: Props) {
  const t = useTranslations("guestMessages");
  const tc = useTranslations("common");
  const [timeline, setTimeline] = useState<GuestMessageTimelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [composeIntent, setComposeIntent] = useState<ComposeIntent>("checkin");
  const [composeHint, setComposeHint] = useState("");
  const [draftId, setDraftId] = useState<number | null>(null);
  const [bodyText, setBodyText] = useState("");
  const [channels, setChannels] = useState<GuestMessageChannels>({});
  const [selectedChannel, setSelectedChannel] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState("");

  const baseUrl = `/api/stay/reception/reservations/${reservationId}/messages`;

  const availableChannels = useMemo(
    () => CHANNEL_ORDER.filter((key) => channels[key]?.available),
    [channels],
  );

  const loadTimeline = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${baseUrl}/?sync=1`);
      if (!res.ok) throw new Error(t("loadFailed"));
      setTimeline((await res.json()) as GuestMessageTimelineItem[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("error"));
      setTimeline([]);
    } finally {
      setLoading(false);
    }
  }, [baseUrl, t, tc]);

  useEffect(() => {
    void loadTimeline();
  }, [loadTimeline]);

  useEffect(() => {
    if (availableChannels.length === 0) {
      setSelectedChannel("");
      return;
    }
    const preferred = channels.default_channel;
    if (
      preferred &&
      availableChannels.includes(preferred as (typeof CHANNEL_ORDER)[number])
    ) {
      setSelectedChannel(preferred);
      return;
    }
    if (!selectedChannel || !availableChannels.includes(selectedChannel as (typeof CHANNEL_ORDER)[number])) {
      setSelectedChannel(availableChannels[0]);
    }
  }, [availableChannels, selectedChannel, channels.default_channel]);

  async function handleCompose() {
    setBusy(true);
    setError("");
    setActionMessage("");
    try {
      const payload: Record<string, string> = { intent: composeIntent };
      if (composeIntent === "reply" && composeHint.trim()) {
        payload.hint = composeHint.trim();
      }
      if (composeIntent === "custom" && composeHint.trim()) {
        payload.hint = composeHint.trim();
      }
      const res = await fetch(`${baseUrl}/compose/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(data?.detail || t("composeFailed"));
      }
      const data = (await res.json()) as GuestMessageComposeResponse;
      setDraftId(data.draft_id);
      setBodyText(data.body_text);
      setChannels(data.channels);
      setActionMessage(t("composeReady"));
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("error"));
    } finally {
      setBusy(false);
    }
  }

  async function handleSend() {
    if (draftId === null) {
      setError(t("composeFirst"));
      return;
    }
    const text = bodyText.trim();
    if (!text) {
      setError(t("emptyBody"));
      return;
    }
    if (!selectedChannel) {
      setError(t("noChannel"));
      return;
    }

    setBusy(true);
    setError("");
    setActionMessage("");
    try {
      const res = await fetch(`${baseUrl}/send/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draft_id: draftId,
          channel: selectedChannel,
          body_text: text,
        }),
      });
      const data = (await res.json().catch(() => null)) as
        | (GuestMessageTimelineItem & { wa_me_url?: string | null })
        | { detail?: string; channel?: string[] }
        | null;
      if (!res.ok) {
        const detail =
          (data && "channel" in data && Array.isArray(data.channel) && data.channel[0]) ||
          (data && "detail" in data && data.detail) ||
          t("sendFailed");
        throw new Error(String(detail));
      }

      if (
        selectedChannel === "whatsapp" &&
        data &&
        "status" in data &&
        data.status === "handoff_whatsapp" &&
        "wa_me_url" in data &&
        data.wa_me_url
      ) {
        window.open(data.wa_me_url, "_blank", "noopener,noreferrer");
        setActionMessage(t("whatsappHandoff"));
      } else {
        setActionMessage(t("sendSuccess"));
      }

      setDraftId(null);
      setBodyText("");
      setComposeHint("");
      await loadTimeline();
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">{t("title")}</h2>
        <button
          type="button"
          className="btn-ghost text-sm"
          onClick={() => void loadTimeline()}
          disabled={loading || busy}
        >
          {tc("refresh")}
        </button>
      </div>

      <div className="max-h-72 space-y-2 overflow-y-auto rounded-lg border bg-stay-surface/40 p-3">
        {loading ? (
          <p className="text-sm text-muted">{tc("loading")}</p>
        ) : timeline.length === 0 ? (
          <p className="text-sm text-muted">{t("empty")}</p>
        ) : (
          timeline.map((item) => {
            const outbound = item.direction === "outbound";
            return (
              <div
                key={`${item.source}-${item.id}`}
                className={`flex ${outbound ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                    outbound
                      ? "rounded-br-md bg-stay-blue text-white"
                      : "rounded-bl-md border bg-white text-stay-navy"
                  }`}
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-xs opacity-80">
                    <span>{timelineChannelLabels(item, t)}</span>
                    <span>{formatMessageTime(item.created_at)}</span>
                    {item.sent_by_name ? <span>{item.sent_by_name}</span> : null}
                  </div>
                  <p className="whitespace-pre-wrap">{item.body_text}</p>
                  {item.document_intake_job_id ? (
                    <p className="mt-1 text-xs opacity-80">
                      OCR #{item.document_intake_job_id}
                    </p>
                  ) : null}
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="space-y-2 rounded-lg border p-3">
        <p className="text-sm font-medium">{t("composeTitle")}</p>
        <div className="flex flex-wrap gap-2">
          {(["checkin", "reply", "custom"] as ComposeIntent[]).map((intent) => (
            <button
              key={intent}
              type="button"
              className={composeIntent === intent ? "btn btn-sm" : "btn-ghost btn-sm"}
              onClick={() => setComposeIntent(intent)}
              disabled={busy}
            >
              {intent === "checkin"
                ? t("intentCheckin")
                : intent === "reply"
                  ? t("intentReply")
                  : t("intentCustom")}
            </button>
          ))}
        </div>
        {composeIntent !== "checkin" ? (
          <label className="block text-sm">
            <span className="mb-1 block text-muted">{t("hintLabel")}</span>
            <input
              className="input w-full"
              value={composeHint}
              onChange={(event) => setComposeHint(event.target.value)}
              placeholder={composeIntent === "reply" ? t("hintReplyPlaceholder") : t("hintCustomPlaceholder")}
              disabled={busy}
            />
          </label>
        ) : null}
        <button type="button" className="btn btn-sm" onClick={() => void handleCompose()} disabled={busy}>
          {busy ? tc("loading") : t("composeAction")}
        </button>
      </div>

      {draftId !== null ? (
        <div className="space-y-2 rounded-lg border p-3">
          <label className="block text-sm">
            <span className="mb-1 block font-medium">{t("bodyLabel")}</span>
            <textarea
              className="input min-h-40 w-full"
              value={bodyText}
              onChange={(event) => setBodyText(event.target.value)}
              disabled={busy}
            />
          </label>

          {availableChannels.length > 0 ? (
            <div className="space-y-1">
              <p className="text-sm font-medium">{t("channelLabel")}</p>
              <div className="flex flex-wrap gap-2">
                {availableChannels.map((channel) => (
                  <label key={channel} className="inline-flex items-center gap-2 text-sm">
                    <input
                      type="radio"
                      name={`guest-message-channel-${reservationId}`}
                      checked={selectedChannel === channel}
                      onChange={() => setSelectedChannel(channel)}
                      disabled={busy}
                    />
                    {t(channelLabelKey(channel))}
                  </label>
                ))}
              </div>
              {selectedChannel ? (
                <p className="text-xs text-muted">
                  {channelHint(selectedChannel, channels, t) ?? null}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-amber-800">{t("noChannel")}</p>
          )}

          <button
            type="button"
            className="btn btn-sm"
            onClick={() => void handleSend()}
            disabled={busy || availableChannels.length === 0}
          >
            {busy ? tc("loading") : t("sendAction")}
          </button>
        </div>
      ) : null}

      {actionMessage ? <p className="text-sm text-green-700">{actionMessage}</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
    </section>
  );
}
