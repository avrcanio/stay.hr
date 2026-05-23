import Link from "next/link";
import { notFound } from "next/navigation";
import { BookingShell } from "@/app/_components/BookingShell";
import { getSiteContext, propertyBasePath, resolvePropertySlug } from "@/lib/site-context";
import { requestHost } from "@/lib/utils";

type Props = { params: Promise<{ slug: string; code: string }> };

export default async function PropertyConfirmationPage({ params }: Props) {
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
        <h1 className="text-2xl font-bold text-teal-800">Rezervacija zaprimljena</h1>
        <p className="text-stone-600">Broj rezervacije:</p>
        <p className="text-3xl font-mono font-bold">{decodeURIComponent(code)}</p>
        <Link href={base || `/p/${slug}`} className="btn inline-flex">
          Natrag na početnu
        </Link>
      </div>
    </BookingShell>
  );
}
