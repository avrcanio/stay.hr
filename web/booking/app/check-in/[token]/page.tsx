import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { GuestCheckInWizard } from "@/app/_components/GuestCheckInWizard";
import { BookingShell } from "@/app/_components/BookingShell";
import { getSiteContext, propertyBasePath, resolvePropertySlug } from "@/lib/site-context";
import { requestHost } from "@/lib/utils";

type Props = { params: Promise<{ token: string }> };

export default async function GuestCheckInPage({ params }: Props) {
  const { token } = await params;
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
  await getTranslations("checkIn");

  return (
    <BookingShell ctx={ctx} propertySlug={propertySlug}>
      <GuestCheckInWizard token={decodeURIComponent(token)} />
    </BookingShell>
  );
}
