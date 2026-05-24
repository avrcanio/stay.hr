import Link from "next/link";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { LanguageSwitcher } from "@/app/_components/LanguageSwitcher";
import { StayLogo } from "@/app/_components/StayLogo";
import { LEGAL_CONTACT, TERMS_SECTIONS } from "@/lib/legal-config";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("terms");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}

export default async function TermsPage() {
  const t = await getTranslations("terms");
  const locale = await getLocale();
  const lastUpdated =
    locale === "hr" ? LEGAL_CONTACT.lastUpdatedHr : LEGAL_CONTACT.lastUpdatedEn;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-stay-border bg-white shadow-sm">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-4">
          <StayLogo href="/" />
          <LanguageSwitcher languages={["hr", "en"]} />
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8">
        <article className="card space-y-8">
          <header className="space-y-2 border-b border-stay-border pb-6">
            <h1 className="text-3xl font-bold text-stay-navy">{t("title")}</h1>
            <p className="text-sm text-stay-muted">{t("lastUpdated", { date: lastUpdated })}</p>
            <p className="text-sm text-stay-muted">
              {t("intro", { controllerName: LEGAL_CONTACT.controllerName })}
            </p>
          </header>

          <dl className="space-y-6">
            {TERMS_SECTIONS.map((sectionId) => (
              <section key={sectionId} className="space-y-2">
                <dt className="text-lg font-semibold text-stay-navy">
                  {t(`sections.${sectionId}.title`)}
                </dt>
                <dd className="whitespace-pre-line text-sm leading-relaxed text-stay-navy/90">
                  {t(`sections.${sectionId}.body`, {
                    controllerName: LEGAL_CONTACT.controllerName,
                    email: LEGAL_CONTACT.infoEmail,
                    privacyEmail: LEGAL_CONTACT.email,
                    address: LEGAL_CONTACT.address,
                    oib: LEGAL_CONTACT.oib,
                  })}
                </dd>
              </section>
            ))}
          </dl>

          <footer className="space-y-3 border-t border-stay-border pt-6 text-sm text-stay-muted">
            <p>{t("contactFooter", { email: LEGAL_CONTACT.infoEmail })}</p>
            <p>
              <Link href="/" className="font-medium text-stay-blue hover:underline">
                {t("homeLink")}
              </Link>
              {" · "}
              <Link href="/privacy" className="font-medium text-stay-blue hover:underline">
                {t("privacyLink")}
              </Link>
            </p>
          </footer>
        </article>
      </main>
    </div>
  );
}
