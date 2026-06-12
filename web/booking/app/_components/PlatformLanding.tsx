import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { LanguageSwitcher } from "@/app/_components/LanguageSwitcher";
import { StayLogo } from "@/app/_components/StayLogo";
import { LEGAL_CONTACT } from "@/lib/legal-config";

function organizationJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: LEGAL_CONTACT.legalName,
    alternateName: [...LEGAL_CONTACT.brandNames],
    url: LEGAL_CONTACT.websiteUrl,
    email: LEGAL_CONTACT.infoEmail,
    taxID: LEGAL_CONTACT.oib,
    address: {
      "@type": "PostalAddress",
      streetAddress: "Bana Josipa Jelačića 58",
      addressLocality: "Šibenik",
      postalCode: "22000",
      addressCountry: "HR",
    },
  };
}

export async function PlatformLanding() {
  const t = await getTranslations("platform");

  return (
    <div className="min-h-screen bg-slate-50">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationJsonLd()) }}
      />

      <header className="border-b border-stay-border bg-white shadow-sm">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-4">
          <StayLogo href="/" />
          <LanguageSwitcher languages={["hr", "en"]} />
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-8 px-4 py-8">
        <section className="card space-y-4">
          <p className="text-sm font-medium uppercase tracking-wide text-stay-blue">
            {t("eyebrow")}
          </p>
          <h1 className="text-3xl font-bold text-stay-navy">{LEGAL_CONTACT.legalName}</h1>
          <p className="text-lg font-medium text-stay-navy">{t("brands")}</p>
          <p className="text-lg text-stay-navy/90">{t("tagline")}</p>
          <p className="text-sm leading-relaxed text-stay-muted">{t("intro")}</p>
          <p className="flex flex-wrap gap-3 pt-1">
            <Link href="/product" className="btn">
              {t("productLink")}
            </Link>
          </p>
          <p className="text-sm">
            <a href={LEGAL_CONTACT.websiteUrl} className="font-medium text-stay-blue hover:underline">
              {LEGAL_CONTACT.websiteUrl}
            </a>
          </p>
        </section>

        <section className="grid gap-4 sm:grid-cols-2">
          <article className="card space-y-2">
            <h2 className="text-lg font-semibold text-stay-navy">{t("services.stay.title")}</h2>
            <p className="text-sm leading-relaxed text-stay-navy/90">{t("services.stay.body")}</p>
          </article>
          <article className="card space-y-2">
            <h2 className="text-lg font-semibold text-stay-navy">{t("services.hospira.title")}</h2>
            <p className="text-sm leading-relaxed text-stay-navy/90">{t("services.hospira.body")}</p>
          </article>
        </section>

        <section className="card space-y-3">
          <h2 className="text-lg font-semibold text-stay-navy">{t("whatsapp.title")}</h2>
          <p className="text-sm leading-relaxed text-stay-navy/90">{t("whatsapp.body")}</p>
          <p className="text-sm">
            <Link href="/privacy" className="font-medium text-stay-blue hover:underline">
              {t("privacyLink")}
            </Link>
          </p>
        </section>

        <section className="card space-y-4">
          <h2 className="text-lg font-semibold text-stay-navy">{t("contact.title")}</h2>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="font-medium text-stay-navy">{t("contact.company")}</dt>
              <dd className="text-stay-muted">{LEGAL_CONTACT.legalName}</dd>
            </div>
            <div>
              <dt className="font-medium text-stay-navy">{t("contact.oib")}</dt>
              <dd className="text-stay-muted">{LEGAL_CONTACT.oib}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="font-medium text-stay-navy">{t("contact.address")}</dt>
              <dd className="text-stay-muted">{LEGAL_CONTACT.address}</dd>
            </div>
            <div>
              <dt className="font-medium text-stay-navy">{t("contact.infoEmail")}</dt>
              <dd>
                <a
                  href={`mailto:${LEGAL_CONTACT.infoEmail}`}
                  className="text-stay-blue hover:underline"
                >
                  {LEGAL_CONTACT.infoEmail}
                </a>
              </dd>
            </div>
            <div>
              <dt className="font-medium text-stay-navy">{t("contact.privacyEmail")}</dt>
              <dd>
                <a href={`mailto:${LEGAL_CONTACT.email}`} className="text-stay-blue hover:underline">
                  {LEGAL_CONTACT.email}
                </a>
              </dd>
            </div>
          </dl>
        </section>

        <footer className="card space-y-3 text-sm text-stay-muted">
          <p>{t("legalNotice")}</p>
          <nav className="flex flex-wrap gap-4">
            <Link href="/privacy" className="font-medium text-stay-blue hover:underline">
              {t("privacyLink")}
            </Link>
            <Link href="/terms" className="font-medium text-stay-blue hover:underline">
              {t("termsLink")}
            </Link>
          </nav>
        </footer>
      </main>
    </div>
  );
}
