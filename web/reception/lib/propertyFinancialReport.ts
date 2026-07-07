export type PropertyFinancialReportGuest = {
  name: string;
  nationality_iso2: string;
  is_primary: boolean;
};

export type PropertyFinancialReportRow = {
  reservation_id: number;
  booking_code: string;
  external_id: string;
  check_in: string;
  check_out: string;
  status: string;
  room_labels: string[];
  nights: number;
  gross: string;
  commission: string | null;
  net: string | null;
  currency: string;
  source: string;
  guests: PropertyFinancialReportGuest[];
};

export type PropertyFinancialReportMeta = {
  property_name: string;
  property_slug: string;
  check_out_from: string;
  check_out_to: string;
  generated_at: string;
  currency: string;
  max_period_days: number;
  rows_with_missing_commission: number;
};

export type PropertyFinancialReportTotals = {
  reservation_count: number;
  nights: number;
  gross: string;
  commission: string;
  net: string;
};

export type PropertyFinancialReport = {
  meta: PropertyFinancialReportMeta;
  rows: PropertyFinancialReportRow[];
  totals: PropertyFinancialReportTotals;
};

export type PropertyFinancialReportErrorCode =
  | "period_invalid"
  | "period_too_long"
  | "property_required"
  | "format_invalid"
  | "no_recipient"
  | "no_smtp"
  | "no_from_address"
  | "send_failed";

export type PropertyFinancialReportSendEmailResult = {
  status: "sent";
  recipients: string[];
  subject?: string;
  reservation_count?: number;
};

const CHANNEX_EXTERNAL_ID_PREFIX = "channex:";

export function isChannexReference(value: string | null | undefined): boolean {
  return (value || "").trim().toLowerCase().startsWith(CHANNEX_EXTERNAL_ID_PREFIX);
}

export function displayBookingReference(row: {
  booking_code: string;
  external_id: string;
}): string {
  const code = (row.booking_code || "").trim();
  if (code && !isChannexReference(code)) return code;
  const externalId = (row.external_id || "").trim();
  if (externalId && !isChannexReference(externalId)) return externalId;
  return "";
}

export function displayExternalReference(row: {
  booking_code: string;
  external_id: string;
}): string {
  const externalId = (row.external_id || "").trim();
  if (!externalId || isChannexReference(externalId)) return "";
  const code = displayBookingReference(row);
  if (externalId === code) return "";
  return externalId;
}

export type PropertyFinancialReportError = {
  code: PropertyFinancialReportErrorCode;
  detail?: string;
  max_days?: number;
};

export function propertyFinancialReportPath(params: {
  propertySlug: string;
  checkOutFrom: string;
  checkOutTo: string;
  format?: "json" | "pdf" | "xlsx";
}): string {
  const query = new URLSearchParams({
    property_slug: params.propertySlug,
    check_out_from: params.checkOutFrom,
    check_out_to: params.checkOutTo,
  });
  if (params.format && params.format !== "json") {
    query.set("format", params.format);
  }
  return `/api/stay/reception/reports/property-financial/?${query.toString()}`;
}

export function propertyFinancialReportSendEmailPath(): string {
  return "/api/stay/reception/reports/property-financial/send-email/";
}

export async function sendPropertyFinancialReportEmail(params: {
  propertySlug: string;
  checkOutFrom: string;
  checkOutTo: string;
  recipients?: string[];
}): Promise<PropertyFinancialReportSendEmailResult> {
  const body: Record<string, unknown> = {
    property_slug: params.propertySlug,
    check_out_from: params.checkOutFrom,
    check_out_to: params.checkOutTo,
  };
  if (params.recipients?.length) {
    body.recipients = params.recipients;
  }

  const res = await fetch(propertyFinancialReportSendEmailPath(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    const parsed = parsePropertyFinancialReportError(payload);
    throw parsed ?? { code: "send_failed" as const };
  }
  return payload as PropertyFinancialReportSendEmailResult;
}

export function parsePropertyFinancialReportError(payload: unknown): PropertyFinancialReportError | null {
  if (!payload || typeof payload !== "object") return null;
  const code = (payload as { code?: unknown }).code;
  if (typeof code !== "string") return null;
  if (
    code !== "period_invalid" &&
    code !== "period_too_long" &&
    code !== "property_required" &&
    code !== "format_invalid" &&
    code !== "no_recipient" &&
    code !== "no_smtp" &&
    code !== "no_from_address" &&
    code !== "send_failed"
  ) {
    return null;
  }
  const detail = (payload as { detail?: unknown }).detail;
  const maxDays = (payload as { max_days?: unknown }).max_days;
  return {
    code,
    detail: typeof detail === "string" ? detail : undefined,
    max_days: typeof maxDays === "number" ? maxDays : undefined,
  };
}
