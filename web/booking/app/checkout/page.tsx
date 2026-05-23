import { notFound } from "next/navigation";
import { BookingShell } from "@/app/_components/BookingShell";
import { CheckoutForm } from "@/app/_components/CheckoutForm";
import { getSiteContext, propertyBasePath, resolvePropertySlug } from "@/lib/site-context";
import { nightsBetween, requestHost } from "@/lib/utils";

type Props = { searchParams: Promise<{ from?: string; to?: string }> };

export default async function CheckoutPage({ searchParams }: Props) {
  const sp = await searchParams;
  const host = await requestHost();
  let ctx;
  try {
    ctx = await getSiteContext(host);
  } catch {
    notFound();
  }

  const propertySlug = resolvePropertySlug(ctx, null);
  if (!propertySlug || !sp.from || !sp.to) {
    notFound();
  }

  const base = propertyBasePath(ctx, propertySlug);
  const action = `${base}/checkout`;

  return (
    <BookingShell ctx={ctx} propertySlug={propertySlug}>
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Checkout</h1>
        <p className="text-sm text-stone-500">
          {sp.from} → {sp.to} ({nightsBetween(sp.from, sp.to)} noći)
        </p>
        <CheckoutForm
          action={action}
          propertySlug={propertySlug}
          checkIn={sp.from}
          checkOut={sp.to}
        />
      </div>
    </BookingShell>
  );
}
