import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { ConfirmationStatus } from "@/app/_components/ConfirmationStatus";
import { BookingShell } from "@/app/_components/BookingShell";
import { getSiteContext, propertyBasePath, resolvePropertySlug } from "@/lib/site-context";
import { requestHost } from "@/lib/utils";

type Props = { params: Promise<{ code: string }> };

export default async function ConfirmationPage({ params }: Props) {
  const { code } = await params;
  const host = await requestHost();
  let ctx;
  try {
    ctx = await getSiteContext(host);
  } catch {
    notFound();
  }

  const propertySlug = resolvePropertySlug(ctx, null);
  if (!propertySlug) {
    notFound();
  }

  const base = propertyBasePath(ctx, propertySlug);
  const bookingCode = decodeURIComponent(code);

  return (
    <BookingShell ctx={ctx} propertySlug={propertySlug}>
      <ConfirmationStatus bookingCode={bookingCode} backHref={base || "/"} />
    </BookingShell>
  );
}
