import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { BookingShell } from "@/app/_components/BookingShell";
import { getSiteContext, propertyBasePath } from "@/lib/site-context";
import { requestHost } from "@/lib/utils";

type Props = { params: Promise<{ slug: string }> };

export default async function PropertyHubPage({ params }: Props) {
  const t = await getTranslations("home");
  const { slug } = await params;
  const host = await requestHost();
  let ctx;
  try {
    ctx = await getSiteContext(host);
  } catch {
    notFound();
  }

  if (ctx.property?.slug) {
    notFound();
  }

  const { stayFetch } = await import("@/lib/stay-server");
  const properties = await stayFetch<{ results: Array<{ slug: string; name: string; address: string }> }>(
    "/api/v1/public/properties",
    { host },
  );
  const prop = properties.results.find((p) => p.slug === slug);
  if (!prop) {
    notFound();
  }

  const base = propertyBasePath(ctx, slug);

  return (
    <BookingShell ctx={ctx} propertySlug={slug}>
      <div className="card space-y-4">
        <h1 className="text-2xl font-bold">{prop.name}</h1>
        {prop.address ? <p className="text-muted">{prop.address}</p> : null}
        <Link href={`${base}/search`} className="btn">
          {t("checkAvailability")}
        </Link>
      </div>
    </BookingShell>
  );
}
