export const GUEST_MESSAGE_DEBUG =
  process.env.NODE_ENV === "development" &&
  process.env.NEXT_PUBLIC_GUEST_MESSAGE_DEBUG === "true";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isValidCorrelationId(value: string): boolean {
  return UUID_RE.test((value || "").trim());
}

/** Generira novi ID samo kad klijent još nema valjanog. */
export function ensureCorrelationId(existing?: string | null): string {
  const trimmed = (existing || "").trim();
  return isValidCorrelationId(trimmed) ? trimmed : crypto.randomUUID();
}

export function sanitizeBody(body: string) {
  const text = (body || "").trim();
  return {
    bodyLength: text.length,
    bodyPreview: text.slice(0, 50) + (text.length > 50 ? "…" : ""),
  };
}

export function logGuestMessageEvent(
  event: string,
  data: Record<string, unknown>,
) {
  if (!GUEST_MESSAGE_DEBUG) return;
  console.log(`[guest-messages] ${event}`, data);
}

export function syncCorrelationIdFromResponse(
  response: Response,
  currentId: string,
): string {
  const echoed = (response.headers.get("X-Correlation-Id") || "").trim();
  return isValidCorrelationId(echoed) ? echoed : currentId;
}
