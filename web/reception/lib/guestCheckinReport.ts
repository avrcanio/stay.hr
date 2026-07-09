export type GuestCheckinKpis = {
  lookback_days: number;
  sessions_created: number;
  sessions_active: number;
  sessions_ready_not_completed: number;
  sessions_ready: number;
  sessions_completed: number;
  sessions_expired: number;
  sessions_revoked: number;
  auto_complete_count: number;
  completion_rate: number | null;
  created_to_ready_seconds_median: number | null;
  ready_to_complete_seconds_median: number | null;
  reminders_sent: number;
  reminders_by_channel: Record<string, { total: number; sent: number }>;
  ocr_jobs_applied: number;
  completed_with_ocr: number;
  completed_manual_only: number;
};

export type GuestCheckinActiveSession = {
  reservation_id: number;
  booking_code: string;
  booker_name: string;
  check_in: string;
  session_status: string;
  effective_status: string;
  ready_at: string | null;
  last_activity_at: string | null;
  progress: {
    required_slots: number;
    ready_slots: number;
    waiting_positions: number[];
    checkin_url: string | null;
  };
};

export type GuestCheckinReport = {
  property_slug: string;
  property_name: string;
  kpis: GuestCheckinKpis;
  active_sessions: GuestCheckinActiveSession[];
};

export function guestCheckinReportPath(params: {
  propertySlug: string;
  days?: number;
}): string {
  const query = new URLSearchParams();
  query.set("property_slug", params.propertySlug);
  if (params.days != null) {
    query.set("days", String(params.days));
  }
  return `/api/stay/reception/reports/guest-checkin/?${query.toString()}`;
}

export function formatDurationSeconds(seconds: number | null | undefined, locale: string): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) {
    return new Intl.NumberFormat(locale).format(hours) + "h " + minutes + "m";
  }
  if (minutes > 0) {
    return minutes + " min";
  }
  return total + " s";
}

export function formatPercent(rate: number | null | undefined, locale: string): string {
  if (rate == null) return "—";
  return new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(rate);
}
