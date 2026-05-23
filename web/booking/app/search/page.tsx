import { notFound } from "next/navigation";
import { SearchView } from "@/app/_components/SearchView";
import { getSiteContext, resolvePropertySlug } from "@/lib/site-context";
import { requestHost } from "@/lib/utils";

type Props = { searchParams: Promise<{ from?: string; to?: string }> };

export default async function SearchPage({ searchParams }: Props) {
  const sp = await searchParams;
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

  return (
    <SearchView
      ctx={ctx}
      host={host}
      propertySlug={propertySlug}
      checkIn={sp.from}
      checkOut={sp.to}
    />
  );
}
