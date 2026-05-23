import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { BookingShell } from "@/app/_components/BookingShell";
import { getSiteContext, propertyBasePath } from "@/lib/site-context";
import { requestHost } from "@/lib/utils";

export default async function HomePage() {
  const t = await getTranslations("home");
  const host = await requestHost();
  let ctx;
  try {
    ctx = await getSiteContext(host);
  } catch {
    notFound();
  }

  if (ctx.property?.slug) {
    const base = propertyBasePath(ctx, ctx.property.slug);
    const name = ctx.property.name;
    const address = ctx.property.address;
    return (
      <BookingShell ctx={ctx} propertySlug={ctx.property.slug}>
        <div className="card space-y-4">
          <h1 className="text-2xl font-bold">{name}</h1>
          {address ? <p className="text-muted">{address}</p> : null}
          <p className="text-muted">{t("selectDates")}</p>
          <Link href={`${base}/search`} className="btn">
            {t("checkAvailability")}
          </Link>
        </div>
      </BookingShell>
    );
  }

  const { stayFetch } = await import("@/lib/stay-server");
  const properties = await stayFetch<{ results: Array<{ slug: string; name: string; address: string }> }>(
    "/api/v1/public/properties",
    { host },
  );

  return (
    <BookingShell ctx={ctx} propertySlug="">
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">{ctx.tenant.name}</h1>
        <p className="text-muted">{t("selectProperty")}</p>
        <ul className="grid gap-3">
          {properties.results.map((p) => (
            <li key={p.slug}>
              <Link href={`/p/${p.slug}`} className="card card-hover block">
                <div className="font-semibold text-stay-navy">{p.name}</div>
                {p.address ? <div className="text-sm text-muted">{p.address}</div> : null}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </BookingShell>
  );
}
