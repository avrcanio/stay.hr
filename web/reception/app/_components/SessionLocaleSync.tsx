"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export function SessionLocaleSync() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;

    async function syncLocale() {
      try {
        const res = await fetch("/api/auth/session");
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as { localeUpdated?: boolean };
        if (data.localeUpdated) {
          router.refresh();
        }
      } catch {
        // Ignore — auth pages handle 401 separately.
      }
    }

    void syncLocale();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return null;
}
