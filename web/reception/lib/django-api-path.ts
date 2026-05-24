/** Django paths that must NOT have a trailing slash (see backend/apps/api/urls.py). */
const NO_TRAILING_SLASH = new Set([
  "app/config",
  "app/fcm-token",
  "public/properties",
  "public/units",
  "public/availability",
  "public/reservations",
]);

export function buildDjangoApiPath(pathSegments: string[]): string {
  const relative = pathSegments.filter(Boolean).join("/");
  const base = `/api/v1/${relative}`;
  if (NO_TRAILING_SLASH.has(relative)) {
    return base;
  }
  if (relative.startsWith("public/reservations/")) {
    return base;
  }
  return base.endsWith("/") ? base : `${base}/`;
}
