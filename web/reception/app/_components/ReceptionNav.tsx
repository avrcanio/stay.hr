"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

type Props = { tenantName?: string };

export function ReceptionNav({ tenantName }: Props) {
  const pathname = usePathname();
  const router = useRouter();

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  const linkClass = (href: string) =>
    `rounded-lg px-3 py-2 text-sm font-medium ${
      pathname === href ? "bg-teal-700 text-white" : "text-stone-600 hover:bg-stone-200"
    }`;

  return (
    <header className="border-b border-stone-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-stone-400">Recepcija</div>
          <div className="font-bold text-teal-900">{tenantName || "Stay.hr"}</div>
        </div>
        <nav className="flex flex-wrap items-center gap-1">
          <Link href="/" className={linkClass("/")}>
            Timeline
          </Link>
          <Link href="/calendar/rooms" className={linkClass("/calendar/rooms")}>
            Kalendar
          </Link>
          <button type="button" onClick={logout} className="btn-ghost ml-2">
            Odjava
          </button>
        </nav>
      </div>
    </header>
  );
}
