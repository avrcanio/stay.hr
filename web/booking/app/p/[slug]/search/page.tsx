import { notFound } from "next/navigation";
import { SearchView } from "@/app/_components/SearchView";
import { getSiteContext, resolvePropertySlug } from "@/lib/site-context";
import { requestHost } from "@/lib/utils";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ from?: string; to?: string }>;
};

export default async function PropertySearchPage({ params, searchParams }: Props) {
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
