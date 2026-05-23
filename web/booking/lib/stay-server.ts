function internalApiBase(): string {
  return (process.env.STAY_API_INTERNAL_URL || "http://stay-django:8000").replace(/\/+$/, "");
}

function bookingToken(): string {
  return (process.env.STAY_BOOKING_API_TOKEN || "").trim();
}

export type StayFetchOptions = {
  host: string;
  method?: string;
  body?: unknown;
  token?: string | null;
  cache?: RequestCache;
};

export async function stayFetch<T>(path: string, opts: StayFetchOptions): Promise<T> {
  const url = `${internalApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  const host = opts.host.split(":")[0].toLowerCase();
  // Node fetch ignores Host; Django resolves tenant from X-Forwarded-Host on internal calls.
  headers["X-Forwarded-Host"] = host;

  const token = opts.token === null ? "" : (opts.token ?? bookingToken());
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, {
    method: opts.method || "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    cache: opts.cache ?? "no-store",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Stay API ${res.status}: ${text.slice(0, 200)}`);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}
