import Link from "next/link";
import type { ReactNode } from "react";
import { getTranslations } from "next-intl/server";
import { LanguageSwitcher } from "@/app/_components/LanguageSwitcher";
import { StayLogo } from "@/app/_components/StayLogo";
import type { SiteContext } from "@/lib/types";
import { propertyBasePath } from "@/lib/site-context";

type Props = {
  ctx: SiteContext;
  propertySlug: string;
  children: ReactNode;
};

export async function BookingShell({ ctx, propertySlug, children }: Props) {
  const t = await getTranslations("nav");
  const base = propertyBasePath(ctx, propertySlug);
  const title =
    (ctx.property?.name as string | undefined) ||
    (ctx.branding?.site_title as string | undefined) ||
    ctx.tenant.name;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-stay-border bg-white shadow-sm">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-4 py-4">
          <div className="flex min-w-0 flex-col gap-0.5">
            <StayLogo href={base || "/"} />
            <span className="truncate text-sm font-semibold text-stay-navy">{title}</span>
          </div>
          <nav className="flex shrink-0 items-center gap-2">
            <Link
              href={`${base}/search`}
              className="rounded-xl px-3 py-2 text-sm font-medium text-stay-muted transition hover:bg-stay-blue-light hover:text-stay-blue"
            >
              {t("booking")}
            </Link>
            <LanguageSwitcher languages={ctx.languages} />
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-8">{children}</main>
    </div>
  );
}
