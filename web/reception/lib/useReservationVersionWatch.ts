"use client";

import { useEffect, useState } from "react";
import { useReservationVersionSse } from "@/lib/useReservationVersionSse";
import { useTimelineVersionPoll } from "@/lib/useTimelineVersionPoll";

export type ReservationVersionTransport = "sse" | "poll";

type Options = {
  reservationId: number;
  scope: string;
  onVersionChange: () => void;
  transport?: ReservationVersionTransport;
  intervalMs?: number;
  enabled?: boolean;
};

/**
 * Watches reservation version for a scope. Default transport is SSE with poll fallback.
 * Panels depend only on `onVersionChange`, not on the transport implementation.
 */
export function useReservationVersionWatch({
  reservationId,
  scope,
  onVersionChange,
  transport = "sse",
  intervalMs,
  enabled = true,
}: Options) {
  const [pollFallback, setPollFallback] = useState(transport === "poll");

  useEffect(() => {
    setPollFallback(transport === "poll");
  }, [transport, reservationId, scope]);

  const useSse = enabled && transport === "sse" && !pollFallback;
  const usePoll = enabled && (transport === "poll" || pollFallback);

  useReservationVersionSse({
    reservationId,
    scope,
    enabled: useSse,
    onVersionChange,
    onUnavailable: () => setPollFallback(true),
  });

  useTimelineVersionPoll({
    reservationId,
    scope,
    intervalMs,
    enabled: usePoll,
    onVersionChange,
  });
}
