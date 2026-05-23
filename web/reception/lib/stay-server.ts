import { cookies } from "next/headers";
import { RECEPTION_SESSION_COOKIE, RECEPTION_TOKEN_COOKIE } from "./types";

function internalApiBase(): string {
  return (process.env.STAY_API_INTERNAL_URL || "http://stay_django:8000").replace(/\/+$/, "");
}

function receptionHost(): string {
  return (process.env.STAY_RECEPTION_HOST || "app.stay.hr").split(":")[0].toLowerCase();
}

export type StayFetchOptions = {
  host?: string;
  method?: string;
  body?: unknown;
  token?: string;
  sessionId?: string;
  cache?: RequestCache;
};

export class StayApiError extends Error {
  status: number;
  body: unknown;
  isNetworkError: boolean;

  constructor(
    message: string,
    opts: { status?: number; body?: unknown; isNetworkError?: boolean } = {},
  ) {
    super(message);
    this.name = "StayApiError";
    this.status = opts.status ?? 0;
    this.body = opts.body ?? null;
    this.isNetworkError = opts.isNetworkError ?? false;
  }
}

function parseErrorBody(text: string): unknown {
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export function getStayApiDetail(body: unknown): string {
  if (typeof body === "string") {
    return body;
  }
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map(String).join("; ");
    }
  }
  return "";
}

export async function getServerSessionId(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(RECEPTION_SESSION_COOKIE)?.value ?? null;
}

export async function getServerToken(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(RECEPTION_TOKEN_COOKIE)?.value ?? null;
}

export function extractSessionIdFromResponse(res: Response): string | null {
  const setCookies =
    typeof res.headers.getSetCookie === "function" ? res.headers.getSetCookie() : [];
  for (const cookie of setCookies) {
    const match = cookie.match(/sessionid=([^;]+)/);
    if (match) {
      return match[1];
    }
  }

  const raw = res.headers.get("set-cookie");
  if (raw) {
    const match = raw.match(/sessionid=([^;]+)/);
    if (match) {
      return match[1];
    }
  }

  return null;
}

export async function buildStayAuthHeaders(
  opts: { host?: string; token?: string; sessionId?: string } = {},
): Promise<Record<string, string> | null> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    Host: opts.host || receptionHost(),
  };

  const sessionId = opts.sessionId ?? (await getServerSessionId());
  const token = opts.token ?? (await getServerToken());

  if (sessionId) {
    headers.Cookie = `sessionid=${sessionId}`;
  } else if (token) {
    headers.Authorization = `Bearer ${token}`;
  } else {
    return null;
  }

  return headers;
}

export async function stayFetch<T>(path: string, opts: StayFetchOptions = {}): Promise<T> {
  const url = `${internalApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = await buildStayAuthHeaders({
    host: opts.host,
    token: opts.token,
    sessionId: opts.sessionId,
  });
  if (!headers) {
    throw new StayApiError("Not authenticated", { status: 401 });
  }

  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method: opts.method || "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      cache: opts.cache ?? "no-store",
    });
  } catch {
    throw new StayApiError("Network error", { isNetworkError: true });
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const body = parseErrorBody(text);
    const detail = getStayApiDetail(body);
    throw new StayApiError(detail || `Stay API ${res.status}`, {
      status: res.status,
      body,
    });
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export async function stayLoginFetch<T>(
  path: string,
  body: unknown,
): Promise<{ data: T; sessionId: string | null; response: Response }> {
  const url = `${internalApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Host: receptionHost(),
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new StayApiError("Network error", { isNetworkError: true });
  }

  const text = await res.text().catch(() => "");
  const parsed = parseErrorBody(text);

  if (!res.ok) {
    if (
      res.status === 409 &&
      parsed &&
      typeof parsed === "object" &&
      "requires_tenant" in parsed &&
      (parsed as { requires_tenant?: boolean }).requires_tenant
    ) {
      return {
        data: parsed as T,
        sessionId: null,
        response: res,
      };
    }

    const detail = getStayApiDetail(parsed);
    throw new StayApiError(detail || `Stay API ${res.status}`, {
      status: res.status,
      body: parsed,
    });
  }

  return {
    data: (parsed ?? {}) as T,
    sessionId: extractSessionIdFromResponse(res),
    response: res,
  };
}

export async function stayLogoutFetch(sessionId: string): Promise<void> {
  const url = `${internalApiBase()}/api/v1/auth/reception-logout/`;
  try {
    await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        Host: receptionHost(),
        Cookie: `sessionid=${sessionId}`,
      },
      cache: "no-store",
    });
  } catch {
    // Best-effort logout; local cookie is cleared regardless.
  }
}
