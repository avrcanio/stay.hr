"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

export function ReportsSubNav() {
  const pathname = usePathname();
  const t = useTranslations("reportsNav");

  const linkClass = (href: string) =>
    `rounded-lg px-3 py-1.5 text-sm font-medium transition ${
      pathname === href
        ? "bg-stay-blue text-white"
        : "text-stay-muted hover:bg-stay-blue-light hover:text-stay-blue"
    }`;

  return (
    <nav className="mb-6 flex flex-wrap gap-2" aria-label={t("title")}>
      <Link href="/reports/property-financial" className={linkClass("/reports/property-financial")}>
        {t("propertyFinancial")}
      </Link>
      <Link href="/reports/booking-reconcile" className={linkClass("/reports/booking-reconcile")}>
        {t("bookingReconcile")}
      </Link>
    </nav>
  );
}
