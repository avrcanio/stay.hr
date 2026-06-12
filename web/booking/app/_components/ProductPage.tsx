import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { LanguageSwitcher } from "@/app/_components/LanguageSwitcher";
import { ProductScreenshotPlaceholder } from "@/app/_components/ProductScreenshotPlaceholder";
import { StayLogo } from "@/app/_components/StayLogo";
import { LEGAL_CONTACT } from "@/lib/legal-config";
import { productScreenshotSrc, type ProductScreenshotId } from "@/lib/product-screenshots";

function ProductBullets({ keys, tPrefix }: { keys: string[]; tPrefix: (key: string) => string }) {
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-stay-navy/90">
      {keys.map((key) => (
        <li key={key}>{tPrefix(key)}</li>
      ))}
    </ul>
  );
}

type ScreenshotItem = {
  id: ProductScreenshotId;
  labelKey: string;
  aspect?: "browser" | "phone";
};

export async function ProductPage() {
  const t = await getTranslations("product");

  const flowStepKeys = ["reservation", "checkIn", "evisitor", "invoice", "cardOptional"] as const;

  const compareRows: Array<{
    key: "timeline" | "calendar" | "mrzNfc" | "push" | "messages" | "statistics" | "cardPayment";
    web: "yes" | "no" | "onRequest";
    hospira: "yes" | "no" | "onRequest";
  }> = [
    { key: "timeline", web: "yes", hospira: "yes" },
    { key: "calendar", web: "yes", hospira: "yes" },
    { key: "mrzNfc", web: "no", hospira: "yes" },
    { key: "push", web: "no", hospira: "yes" },
    { key: "messages", web: "yes", hospira: "yes" },
    { key: "statistics", web: "no", hospira: "yes" },
    { key: "cardPayment", web: "no", hospira: "onRequest" },
  ];

  const compareCell = (value: "yes" | "no" | "onRequest") => {
    if (value === "yes") return t("compareYes");
    if (value === "onRequest") return t("compareOnRequest");
    return t("compareNo");
  };

  const faqKeys = ["webVsApp", "deviceToken", "cardPayment", "languages"] as const;

  const bookingScreenshots: ScreenshotItem[] = [
    { id: "bookingSearch", labelKey: "screenshotSearch" },
    { id: "bookingCheckout", labelKey: "screenshotCheckout" },
  ];

  const receptionScreenshots: ScreenshotItem[] = [
    { id: "receptionTimeline", labelKey: "screenshotTimeline" },
    { id: "receptionCalendar", labelKey: "screenshotCalendar" },
    { id: "receptionDetail", labelKey: "screenshotDetail" },
  ];

  const hospiraScreenshots: ScreenshotItem[] = [
    { id: "hospiraTimeline", labelKey: "screenshotTimeline", aspect: "phone" },
    { id: "hospiraCalendarRooms", labelKey: "screenshotCalendarRooms", aspect: "phone" },
    { id: "hospiraCalendarOccupancy", labelKey: "screenshotCalendarOccupancy", aspect: "phone" },
    { id: "hospiraMessages", labelKey: "screenshotMessages", aspect: "phone" },
    { id: "hospiraReviews", labelKey: "screenshotReviews", aspect: "phone" },
    { id: "hospiraStatisticsMonthly", labelKey: "screenshotStatisticsMonthly", aspect: "phone" },
    { id: "hospiraStatisticsAnnual", labelKey: "screenshotStatisticsAnnual", aspect: "phone" },
  ];

  function renderScreenshots(
    items: ScreenshotItem[],
    section: "booking" | "reception" | "hospira",
    gridClass: string,
  ) {
    return (
      <div className={gridClass}>
        {items.map((item) => (
          <ProductScreenshotPlaceholder
            key={item.id}
            label={t(`${section}.${item.labelKey}`)}
            hint={t("placeholderHint")}
            aspect={item.aspect ?? "browser"}
            src={productScreenshotSrc(item.id)}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-stay-border bg-white shadow-sm">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-4 py-4">
          <StayLogo href="/" />
          <LanguageSwitcher languages={["hr", "en"]} />
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-8 px-4 py-8">
        <p className="text-sm">
          <Link href="/" className="font-medium text-stay-blue hover:underline">
            ← {t("backHome")}
          </Link>
        </p>

        <section className="card space-y-4">
          <p className="text-sm font-medium uppercase tracking-wide text-stay-blue">{t("eyebrow")}</p>
          <h1 className="text-3xl font-bold text-stay-navy">{t("heroTitle")}</h1>
          <p className="text-lg font-medium text-stay-navy/90">{t("heroSubtitle")}</p>
          <p className="text-sm leading-relaxed text-stay-muted">{t("heroIntro")}</p>
        </section>

        <section className="card space-y-4">
          <h2 className="text-lg font-semibold text-stay-navy">{t("flowTitle")}</h2>
          <ol className="flex flex-wrap items-center gap-2 text-sm">
            {flowStepKeys.map((step, index) => (
              <li key={step} className="flex items-center gap-2">
                <span
                  className={`rounded-full px-3 py-1 font-medium ${
                    step === "cardOptional"
                      ? "border border-dashed border-stay-blue bg-stay-blue-light text-stay-blue"
                      : "bg-stay-blue text-white"
                  }`}
                >
                  {t(`flowSteps.${step}`)}
                </span>
                {index < flowStepKeys.length - 1 ? (
                  <span className="text-stay-muted" aria-hidden="true">
                    →
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        </section>

        <section className="space-y-6">
          <h2 className="text-xl font-bold text-stay-navy">{t("productsTitle")}</h2>

          <article className="card space-y-4">
            <header className="space-y-2">
              <h3 className="text-lg font-semibold text-stay-navy">{t("booking.title")}</h3>
              <p className="text-sm text-stay-muted">{t("booking.audience")}</p>
              <p className="text-sm leading-relaxed text-stay-navy/90">{t("booking.intro")}</p>
            </header>
            <ProductBullets
              keys={["bullet1", "bullet2", "bullet3", "bullet4", "bullet5", "bullet6"]}
              tPrefix={(key) => t(`booking.${key}`)}
            />
            {renderScreenshots(bookingScreenshots, "booking", "grid gap-4 sm:grid-cols-2")}
          </article>

          <article className="card space-y-4">
            <header className="space-y-2">
              <h3 className="text-lg font-semibold text-stay-navy">{t("reception.title")}</h3>
              <p className="text-sm text-stay-muted">{t("reception.audience")}</p>
              <p className="text-sm leading-relaxed text-stay-navy/90">{t("reception.intro")}</p>
            </header>
            <ProductBullets
              keys={["bullet1", "bullet2", "bullet3", "bullet4", "bullet5", "bullet6", "bullet7"]}
              tPrefix={(key) => t(`reception.${key}`)}
            />
            {renderScreenshots(
              receptionScreenshots.slice(0, 2),
              "reception",
              "grid gap-4 sm:grid-cols-2",
            )}
            {renderScreenshots(receptionScreenshots.slice(2), "reception", "grid gap-4")}
          </article>

          <article className="card space-y-4">
            <header className="space-y-2">
              <h3 className="text-lg font-semibold text-stay-navy">{t("hospira.title")}</h3>
              <p className="text-sm text-stay-muted">{t("hospira.audience")}</p>
              <p className="text-sm leading-relaxed text-stay-navy/90">{t("hospira.intro")}</p>
            </header>
            <ProductBullets
              keys={[
                "bullet1",
                "bullet2",
                "bullet3",
                "bullet4",
                "bullet5",
                "bullet6",
                "bullet7",
                "bullet8",
                "bullet9",
              ]}
              tPrefix={(key) => t(`hospira.${key}`)}
            />
            {renderScreenshots(
              hospiraScreenshots,
              "hospira",
              "grid gap-4 sm:grid-cols-2 lg:grid-cols-3",
            )}
          </article>
        </section>

        <section className="card space-y-4 overflow-x-auto">
          <h2 className="text-lg font-semibold text-stay-navy">{t("compareTitle")}</h2>
          <table className="product-table">
            <thead>
              <tr>
                <th scope="col">{t("compareFeature")}</th>
                <th scope="col">{t("compareWeb")}</th>
                <th scope="col">{t("compareHospira")}</th>
              </tr>
            </thead>
            <tbody>
              {compareRows.map((row) => (
                <tr key={row.key}>
                  <td data-label={`${t("compareFeature")}: `}>{t(`compareRows.${row.key}`)}</td>
                  <td data-label={`${t("compareWeb")}: `}>{compareCell(row.web)}</td>
                  <td data-label={`${t("compareHospira")}: `}>{compareCell(row.hospira)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card space-y-3">
          <h2 className="text-lg font-semibold text-stay-navy">{t("extensionsTitle")}</h2>
          <article className="space-y-3 rounded-xl border border-stay-border bg-slate-50 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold text-stay-navy">{t("cardTitle")}</h3>
              <span className="badge bg-stay-blue-light text-stay-blue">{t("cardBadge")}</span>
            </div>
            <p className="text-sm leading-relaxed text-stay-navy/90">{t("cardBody")}</p>
            <p>
              <a
                href={`mailto:${LEGAL_CONTACT.infoEmail}?subject=${encodeURIComponent(t("cardTitle"))}`}
                className="btn"
              >
                {t("cardCta")}
              </a>
            </p>
          </article>
        </section>

        <section className="card space-y-4">
          <h2 className="text-lg font-semibold text-stay-navy">{t("faqTitle")}</h2>
          <dl className="space-y-4">
            {faqKeys.map((key) => (
              <div key={key} className="space-y-1">
                <dt className="text-sm font-semibold text-stay-navy">{t(`faq.${key}Q`)}</dt>
                <dd className="text-sm leading-relaxed text-stay-navy/90">{t(`faq.${key}A`)}</dd>
              </div>
            ))}
          </dl>
        </section>

        <footer className="card space-y-3 text-sm text-stay-muted">
          <p>
            {t("footerContact")}{" "}
            <a href={`mailto:${LEGAL_CONTACT.infoEmail}`} className="text-stay-blue hover:underline">
              {LEGAL_CONTACT.infoEmail}
            </a>
          </p>
          <nav className="flex flex-wrap gap-4">
            <Link href="/" className="font-medium text-stay-blue hover:underline">
              {t("homeLink")}
            </Link>
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
