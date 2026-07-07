"use client";

import { useEffect, useRef } from "react";
import type { ReservationVersionsResponse } from "@/lib/types";

type Options = {
  reservationId: number;
  scope: string;
  onVersionChange: () => void;
  intervalMs?: number;
  enabled?: boolean;
};

/**
 * Polls reservation version for a single scope (e.g. `messages`).
 * Calls `onVersionChange` when `versions[scope]` increases; pauses while the tab is hidden.
 */
export function useTimelineVersionPoll({
  reservationId,
  scope,
  onVersionChange,
  intervalMs = 5_000,
  enabled = true,
}: Options) {
  const etagRef = useRef<string | null>(null);
  const versionRef = useRef<number | null>(null);
  const onVersionChangeRef = useRef(onVersionChange);
  onVersionChangeRef.current = onVersionChange;

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    let intervalId: number | null = null;

    async function poll(isSeed: boolean) {
      if (document.hidden) return;

      try {
        const headers: HeadersInit = {};
        if (!isSeed && etagRef.current) {
          headers["If-None-Match"] = etagRef.current;
        }

        const params = new URLSearchParams({
          reservation_id: String(reservationId),
          scope,
        });
        const res = await fetch(`/api/stay/reception/sync-versions/?${params}`, {
          headers,
        });
        if (cancelled) return;

        const etag = res.headers.get("ETag");
        if (etag) {
          etagRef.current = etag;
        }

        if (res.status === 304) return;
        if (!res.ok) return;

        const data = (await res.json()) as ReservationVersionsResponse;
        const nextVersion = data.versions[scope];

        if (
          !isSeed &&
          versionRef.current !== null &&
          nextVersion !== versionRef.current
        ) {
          onVersionChangeRef.current();
        }
        versionRef.current = nextVersion;
      } catch {
        // Ignore network errors during background poll.
      }
    }

    function startPolling() {
      void poll(versionRef.current === null);
      if (intervalId !== null) {
        window.clearInterval(intervalId);
      }
      intervalId = window.setInterval(() => {
        void poll(false);
      }, intervalMs);
    }

    function stopPolling() {
      if (intervalId !== null) {
        window.clearInterval(intervalId);
        intervalId = null;
      }
    }

    function onVisibilityChange() {
      if (document.hidden) {
        stopPolling();
        return;
      }
      startPolling();
    }

    if (!document.hidden) {
      startPolling();
    }

    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      stopPolling();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      etagRef.current = null;
      versionRef.current = null;
    };
  }, [enabled, intervalMs, reservationId, scope]);
}
