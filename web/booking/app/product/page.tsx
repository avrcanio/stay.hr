import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { ProductPage } from "@/app/_components/ProductPage";
import { isPlatformApexHost } from "@/lib/platform-host";
import { requestHost } from "@/lib/utils";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("product");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}

export default async function ProductRoutePage() {
  const host = await requestHost();
  if (!isPlatformApexHost(host)) {
    notFound();
  }

  return <ProductPage />;
}
