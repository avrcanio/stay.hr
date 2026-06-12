import { getTranslations } from "next-intl/server";
import { ProductChannelList } from "@/app/_components/ProductChannelList";
import { allChannels, featuredChannels } from "@/lib/channex-channels";

export async function ProductChannelManagerSection() {
  const t = await getTranslations("product.channelManager");
  const featured = featuredChannels();
  const channels = allChannels();

  return (
    <section className="card space-y-4">
      <header className="space-y-2">
        <h2 className="text-lg font-semibold text-stay-navy">{t("title")}</h2>
        <p className="text-sm leading-relaxed text-stay-navy/90">{t("intro")}</p>
      </header>

      <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-stay-navy/90">
        <li>{t("bullet1")}</li>
        <li>{t("bullet2")}</li>
        <li>{t("bullet3")}</li>
        <li>{t("bullet4")}</li>
      </ul>

      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-stay-navy">{t("featuredTitle")}</h3>
        <ul className="grid gap-2 sm:grid-cols-2 md:grid-cols-3">
          {featured.map((channel) => (
            <li
              key={channel.code}
              className="rounded-xl border border-stay-border bg-slate-50 px-3 py-2 text-sm"
            >
              <span className="font-medium text-stay-navy">{channel.name}</span>
              <span className="mt-0.5 block text-xs text-stay-muted">
                {t("codeLabel")}: {channel.code}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <ProductChannelList
        channels={channels}
        allTitle={t("allTitle")}
        allCountLabel={t("allCount", { count: channels.length })}
        expandLabel={t("expandAll")}
        collapseLabel={t("collapseAll")}
      />

      <p className="text-xs text-stay-muted">{t("sourceNote")}</p>
    </section>
  );
}
