"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

export function WhatsAppSubNav() {
  const pathname = usePathname();
  const t = useTranslations("whatsapp.nav");

  const links = [
    { href: "/whatsapp/overview", label: t("overview") },
    { href: "/whatsapp/templates", label: t("templates") },
    { href: "/whatsapp/settings", label: t("settings") },
  ];

  return (
    <nav className="mb-6 flex flex-wrap gap-2 border-b border-stay-border pb-3">
      {links.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
            pathname === link.href
              ? "bg-stay-blue text-white"
              : "text-stay-muted hover:bg-stay-blue-light hover:text-stay-blue"
          }`}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
