"use client";

import { useEffect, useRef } from "react";

type Options = {
  reservationId: number;
  scope: string;
  onVersionChange: () => void;
  onUnavailable?: () => void;
  enabled?: boolean;
};

function streamUrl(reservationId: number, scope: string): string {
  const params = new URLSearchParams({
    reservation_id: String(reservationId),
    scope,
  });
  return `/api/stay/reception/reservation-versions/stream/?${params}`;
}

/**
 * SSE transport for reservation version changes.
 * Calls `onVersionChange` when `version` increases for the watched scope.
 */
export function useReservationVersionSse({
  reservationId,
  scope,
  onVersionChange,
  onUnavailable,
  enabled = true,
}: Options) {
  const versionRef = useRef<number | null>(null);
  const onVersionChangeRef = useRef(onVersionChange);
  const onUnavailableRef = useRef(onUnavailable);
  onVersionChangeRef.current = onVersionChange;
  onUnavailableRef.current = onUnavailable;

  useEffect(() => {
    if (!enabled) return;

    let source: EventSource | null = null;
    let reconnectTimer: number | null = null;
    let cancelled = false;

    function clearReconnect() {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function scheduleReconnect() {
      if (cancelled || document.hidden) return;
      clearReconnect();
      reconnectTimer = window.setTimeout(() => {
        connect();
      }, 3_000);
    }

    function handleVersion(version: number, isSeed: boolean) {
      if (
        !isSeed &&
        versionRef.current !== null &&
        version !== versionRef.current
      ) {
        onVersionChangeRef.current();
      }
      versionRef.current = version;
    }

    function connect() {
      if (cancelled || document.hidden) return;

      source?.close();
      source = new EventSource(streamUrl(reservationId, scope));

      source.addEventListener("connected", (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data) as {
            version?: number;
          };
          if (typeof data.version === "number") {
            handleVersion(data.version, versionRef.current === null);
          }
        } catch {
          // Ignore malformed connected payload.
        }
      });

      source.addEventListener("reservation_version_changed", (event) => {
        try {
          const data = JSON.parse((event as MessageEvent).data) as {
            version?: number;
          };
          if (typeof data.version === "number") {
            handleVersion(data.version, false);
          }
        } catch {
          // Ignore malformed event payload.
        }
      });

      source.onerror = () => {
        source?.close();
        source = null;
        if (onUnavailableRef.current) {
          onUnavailableRef.current();
          return;
        }
        scheduleReconnect();
      };
    }

    function onVisibilityChange() {
      if (document.hidden) {
        clearReconnect();
        source?.close();
        source = null;
        return;
      }
      connect();
    }

    if (!document.hidden) {
      connect();
    }

    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      clearReconnect();
      source?.close();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      versionRef.current = null;
    };
  }, [enabled, reservationId, scope]);
}
