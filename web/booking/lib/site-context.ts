import type { SiteContext } from "./types";
import { stayFetch } from "./stay-server";

export async function getSiteContext(host: string): Promise<SiteContext> {
  return stayFetch<SiteContext>("/api/v1/public/site-context/", {
    host,
    token: null,
  });
}

export function resolvePropertySlug(
  ctx: SiteContext,
  pathSlug?: string | null,
): string | null {
  if (ctx.property?.slug) {
    return ctx.property.slug;
  }
  return pathSlug?.trim() || null;
}

export function propertyBasePath(ctx: SiteContext, propertySlug: string): string {
  if (ctx.property?.slug) {
    return "";
  }
  return `/p/${propertySlug}`;
}
