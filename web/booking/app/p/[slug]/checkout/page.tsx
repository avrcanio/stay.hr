import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { BookingShell } from "@/app/_components/BookingShell";
import { CheckoutForm } from "@/app/_components/CheckoutForm";
import { getSiteContext, propertyBasePath, resolvePropertySlug } from "@/lib/site-context";
import { nightsBetween, requestHost } from "@/lib/utils";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ from?: string; to?: string; unit_id?: string }>;
};

export default async function PropertyCheckoutPage({ params, searchParams }: Props) {
  const t = await getTranslations("checkout");
  const { slug } = await params;
  const sp = await searchParams;
  const host = await requestHost();
  let ctx;
  try {
    ctx = await getSiteContext(host);
  } catch {
    notFound();
  }

  const propertySlug = resolvePropertySlug(ctx, slug);
  const unitId = sp.unit_id ? Number.parseInt(sp.unit_id, 10) : NaN;
  if (!propertySlug || !sp.from || !sp.to || !Number.isFinite(unitId)) {
    notFound();
  }

  const base = propertyBasePath(ctx, propertySlug);
  const action = `${base}/checkout?from=${sp.from}&to=${sp.to}&unit_id=${unitId}`;

  return (
    <BookingShell ctx={ctx} propertySlug={propertySlug}>
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <p className="text-sm text-muted">
          {t("dateRange", { from: sp.from, to: sp.to, nights: nightsBetween(sp.from, sp.to) })}
        </p>
        <CheckoutForm
          action={action}
          propertySlug={propertySlug}
          unitId={unitId}
          checkIn={sp.from}
          checkOut={sp.to}
        />
      </div>
    </BookingShell>
  );
}
