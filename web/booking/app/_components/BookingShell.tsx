import Link from "next/link";
import type { ReactNode } from "react";
import type { SiteContext } from "@/lib/types";
import { propertyBasePath } from "@/lib/site-context";

type Props = {
  ctx: SiteContext;
  propertySlug: string;
  children: ReactNode;
};

export function BookingShell({ ctx, propertySlug, children }: Props) {
  const base = propertyBasePath(ctx, propertySlug);
  const title =
    (ctx.property?.name as string | undefined) ||
    (ctx.branding?.site_title as string | undefined) ||
    ctx.tenant.name;

  return (
    <div className="min-h-screen">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
          <Link href={base || "/"} className="text-lg font-bold text-teal-800">
            {title}
          </Link>
          <nav className="flex gap-4 text-sm font-medium text-stone-600">
            <Link href={`${base}/search`} className="hover:text-teal-700">
              Rezervacija
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-8">{children}</main>
    </div>
  );
}
