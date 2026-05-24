"use client";

import { useEffect, useRef } from "react";

type Options = {
  onStale: () => void;
  intervalMs?: number;
  year?: number;
  enabled?: boolean;
};

export function useSyncVersionsPoll({
  onStale,
  intervalMs = 30_000,
  year = new Date().getFullYear(),
  enabled = true,
}: Options) {
  const etagRef = useRef<string | null>(null);
  const onStaleRef = useRef(onStale);
  onStaleRef.current = onStale;

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;

    async function poll(isSeed: boolean) {
      try {
        const headers: HeadersInit = {};
        if (!isSeed && etagRef.current) {
          headers["If-None-Match"] = etagRef.current;
        }

        const res = await fetch(`/api/stay/reception/sync-versions/?year=${year}`, {
          headers,
        });
        if (cancelled) return;

        const etag = res.headers.get("ETag");
        if (etag) {
          etagRef.current = etag;
        }

        if (isSeed || res.status !== 200) {
          return;
        }

        onStaleRef.current();
      } catch {
        // Ignore network errors during background poll.
      }
    }

    void poll(true);

    const id = window.setInterval(() => {
      void poll(false);
    }, intervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [enabled, intervalMs, year]);
}
