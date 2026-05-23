import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { BookingShell } from "@/app/_components/BookingShell";
import { getSiteContext, propertyBasePath, resolvePropertySlug } from "@/lib/site-context";
import { requestHost } from "@/lib/utils";

type Props = { params: Promise<{ slug: string; code: string }> };

export default async function PropertyConfirmationPage({ params }: Props) {
  const t = await getTranslations("confirmation");
  const { slug, code } = await params;
  const host = await requestHost();
  let ctx;
  try {
    ctx = await getSiteContext(host);
  } catch {
    notFound();
  }

  const propertySlug = resolvePropertySlug(ctx, slug);
  if (!propertySlug) {
    notFound();
  }

  const base = propertyBasePath(ctx, propertySlug);

  return (
    <BookingShell ctx={ctx} propertySlug={propertySlug}>
      <div className="card space-y-4 text-center">
        <h1 className="text-2xl font-bold text-stay-blue">{t("title")}</h1>
        <p className="text-muted">{t("codeLabel")}</p>
        <p className="font-mono text-3xl font-bold text-stay-navy">{decodeURIComponent(code)}</p>
        <Link href={base || `/p/${slug}`} className="btn inline-flex">
          {t("backHome")}
        </Link>
      </div>
    </BookingShell>
  );
}
