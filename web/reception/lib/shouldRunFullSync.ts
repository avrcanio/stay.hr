/** Interval for periodic `sync=1` while the panel stays open. */
export const FULL_SYNC_INTERVAL_MS = 5 * 60 * 1000;

/** After tab hidden this long, return triggers `sync=1`. */
export const VISIBILITY_STALE_MS = 2 * 60 * 1000;

export type FullSyncContext = {
  /** First load for this reservation / panel mount. */
  isMount?: boolean;
  /** Timestamp when the tab last became hidden; null if never hidden this session. */
  hiddenAt: number | null;
  /** Tab just became visible again. */
  visibleAgain?: boolean;
  /** Timestamp of the last `sync=1` fetch. */
  lastFullSyncAt: number | null;
  now: number;
};

/**
 * Single decision point for `sync=1` on the guest messages timeline.
 * All other refreshes should use `sync=0` (background).
 */
export function shouldRunFullSync(ctx: FullSyncContext): boolean {
  if (ctx.isMount) return true;

  if (ctx.visibleAgain && ctx.hiddenAt !== null) {
    if (ctx.now - ctx.hiddenAt >= VISIBILITY_STALE_MS) return true;
  }

  if (ctx.lastFullSyncAt === null) return true;
  if (ctx.now - ctx.lastFullSyncAt >= FULL_SYNC_INTERVAL_MS) return true;

  return false;
}
