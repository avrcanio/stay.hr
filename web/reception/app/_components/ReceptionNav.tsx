"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { SessionLocaleSync } from "@/app/_components/SessionLocaleSync";
import { StayLogo } from "@/app/_components/StayLogo";

type Props = { tenantName?: string };

export function ReceptionNav({ tenantName }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations("nav");

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  const linkClass = (href: string) =>
    `rounded-xl px-3 py-2 text-sm font-medium transition ${
      pathname === href
        ? "bg-stay-blue text-white shadow-sm"
        : "text-stay-muted hover:bg-stay-blue-light hover:text-stay-blue"
    }`;

  return (
    <header className="border-b border-stay-border bg-white shadow-sm">
      <SessionLocaleSync />
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex min-w-0 flex-col gap-1">
          <StayLogo href="/" subtitle={t("reception")} />
          {tenantName ? (
            <div className="truncate pl-0.5 text-sm font-semibold text-stay-navy">{tenantName}</div>
          ) : null}
        </div>
        <nav className="flex flex-wrap items-center gap-1">
          <Link href="/" className={linkClass("/")}>
            {t("timeline")}
          </Link>
          <Link href="/calendar/rooms" className={linkClass("/calendar/rooms")}>
            {t("calendar")}
          </Link>
          <button type="button" onClick={logout} className="btn-ghost ml-2">
            {t("logout")}
          </button>
        </nav>
      </div>
    </header>
  );
}
