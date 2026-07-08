export type BookingReconcileFieldKey =
  | "amount"
  | "commission_amount"
  | "check_in"
  | "check_out"
  | "status"
  | "units_count";

export type BookingReconcileMatchKind =
  | "matched"
  | "missing_in_stay"
  | "missing_in_booking"
  | "parse_error";

export type BookingFieldDiff = {
  field_key: BookingReconcileFieldKey;
  field_label: string;
  booking_value: string | number | null;
  stay_value: string | number | null;
  booking_display: string;
  stay_display: string;
  severity: "info" | "warning" | "error";
  fixable: boolean;
  block_reasons: string[];
};

export type BookingReconcileRow = {
  row_key: string;
  booking_code: string;
  booking_external_id: string;
  match_kind: BookingReconcileMatchKind;
  reservation_id: number | null;
  guest_name: string;
  booking_status: string;
  stay_status: string | null;
  booking_amount: string | null;
  stay_amount: string | null;
  booking_commission: string | null;
  stay_commission: string | null;
  check_in: string | null;
  check_out: string | null;
  differences: BookingFieldDiff[];
  parse_error: string | null;
  has_differences: boolean;
  is_fixable: boolean;
};

export type BookingReconcileSummary = {
  total_rows: number;
  matched: number;
  missing_in_stay: number;
  missing_in_booking: number;
  parse_errors: number;
  rows_with_differences: number;
  fixable_rows: number;
  booking_total_amount: string;
  stay_total_amount: string;
  booking_total_commission: string;
  stay_total_commission: string;
};

export type BookingReconcileResult = {
  snapshot_id: string | null;
  meta: {
    tenant_id: number;
    property_id: number;
    property_slug: string;
    filename: string;
    date_axis: "check_out" | "check_in" | null;
    date_from: string | null;
    date_to: string | null;
    generated_at: string;
    parser_version: string;
  };
  summary: BookingReconcileSummary;
  rows: BookingReconcileRow[];
};

export type BookingReconcileApplyRowResult = {
  booking_code: string;
  applied: boolean;
  skipped: boolean;
  reason: string;
  reservation_id: number | null;
};

export type BookingReconcileApplyResult = {
  results: BookingReconcileApplyRowResult[];
};

export type BookingReconcileApplyItem = {
  booking_code: string;
  fields?: BookingReconcileFieldKey[];
  mode?: "fill_empty" | "overwrite";
};

export function bookingReconcileComparePath(): string {
  return "/api/stay/reception/reports/booking-reconcile/compare/";
}

export function bookingReconcileApplyPath(): string {
  return "/api/stay/reception/reports/booking-reconcile/apply/";
}

export async function compareBookingExport(params: {
  file: File;
  propertySlug: string;
  dateAxis?: "check_out" | "check_in" | "";
  dateFrom?: string;
  dateTo?: string;
}): Promise<BookingReconcileResult> {
  const formData = new FormData();
  formData.append("file", params.file);
  formData.append("property_slug", params.propertySlug);
  if (params.dateAxis) formData.append("date_axis", params.dateAxis);
  if (params.dateFrom) formData.append("date_from", params.dateFrom);
  if (params.dateTo) formData.append("date_to", params.dateTo);

  const res = await fetch(bookingReconcileComparePath(), {
    method: "POST",
    body: formData,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      (typeof data?.detail === "string" && data.detail) ||
      data?.code ||
      "compare_failed";
    throw new Error(detail);
  }
  return data as BookingReconcileResult;
}

export function bookingReconcileRecomparePath(): string {
  return "/api/stay/reception/reports/booking-reconcile/recompare/";
}

export async function recompareBookingExport(params: {
  snapshotId: string;
  propertySlug: string;
}): Promise<BookingReconcileResult> {
  const res = await fetch(bookingReconcileRecomparePath(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      snapshot_id: params.snapshotId,
      property_slug: params.propertySlug,
    }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      (typeof data?.detail === "string" && data.detail) ||
      data?.code ||
      "recompare_failed";
    throw new Error(detail);
  }
  return data as BookingReconcileResult;
}

export async function applyBookingReconcileFixes(params: {
  snapshotId: string;
  propertySlug: string;
  mode: "fill_empty" | "overwrite";
  confirmOverwrite?: boolean;
  items: BookingReconcileApplyItem[];
}): Promise<BookingReconcileApplyResult> {
  const res = await fetch(bookingReconcileApplyPath(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      snapshot_id: params.snapshotId,
      property_slug: params.propertySlug,
      mode: params.mode,
      confirm_overwrite: params.confirmOverwrite ?? false,
      items: params.items,
    }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      (typeof data?.detail === "string" && data.detail) ||
      data?.code ||
      "apply_failed";
    throw new Error(detail);
  }
  return data as BookingReconcileApplyResult;
}

export function fixableFieldKeys(row: BookingReconcileRow): BookingReconcileFieldKey[] {
  if (row.match_kind === "missing_in_stay") return [];
  return row.differences
    .filter((diff) => diff.fixable && diff.block_reasons.length === 0)
    .map((diff) => diff.field_key);
}
