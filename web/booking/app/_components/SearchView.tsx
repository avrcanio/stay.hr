import Link from "next/link";
import { getTranslations } from "next-intl/server";
import type { SiteContext } from "@/lib/types";
import { propertyBasePath } from "@/lib/site-context";
import { addDaysIso, nightsBetween, todayIso } from "@/lib/utils";
import { stayFetch } from "@/lib/stay-server";
import type { AvailabilityResponse, PublicUnit } from "@/lib/types";
import { BookingShell } from "@/app/_components/BookingShell";
import { SearchDateForm } from "@/app/_components/SearchDateForm";

type Props = {
  ctx: SiteContext;
  host: string;
  propertySlug: string;
  checkIn?: string;
  checkOut?: string;
};

export async function SearchView({ ctx, host, propertySlug, checkIn, checkOut }: Props) {
  const t = await getTranslations("search");
  const from = checkIn || todayIso();
  const to = checkOut && checkOut > from ? checkOut : addDaysIso(from, 2);
  const base = propertyBasePath(ctx, propertySlug);

  const unitsRes = await stayFetch<{ results: PublicUnit[] }>(
    `/api/v1/public/units?property=${encodeURIComponent(propertySlug)}`,
    { host },
  );

  let availability: AvailabilityResponse | null = null;
  let availabilityError = false;
  try {
    availability = await stayFetch<AvailabilityResponse>(
      `/api/v1/public/availability?from=${from}&to=${to}&property=${encodeURIComponent(propertySlug)}`,
      { host },
    );
  } catch {
    availability = null;
    availabilityError = true;
  }

  const nights = nightsBetween(from, to);
  const propertyName = ctx.property?.name || propertySlug;

  return (
    <BookingShell ctx={ctx} propertySlug={propertySlug}>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">{t("title", { property: propertyName })}</h1>
          <p className="text-sm text-muted">
            {t("dateRange", { from, to, nights })}
          </p>
        </div>

        <SearchDateForm initialFrom={from} initialTo={to} />

        {availabilityError ? (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {t("availabilityError")}
          </p>
        ) : null}

        <ul className="space-y-3">
          {unitsRes.results.map((unit) => {
            const avail = availability?.units.find((u) => u.unit_id === unit.id);
            const blocked = (avail?.blocked_periods?.length ?? 0) > 0;
            return (
              <li key={unit.id} className="card flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-semibold text-stay-navy">
                    {unit.code} — {unit.name}
                  </div>
                  <div className="text-sm text-muted">{t("maxGuests", { count: unit.capacity_max_guests })}</div>
                  {availabilityError ? (
                    <div className="text-xs text-amber-700">—</div>
                  ) : blocked ? (
                    <div className="text-xs font-medium text-amber-700">{t("occupied")}</div>
                  ) : (
                    <div className="text-xs font-medium text-stay-blue">{t("available")}</div>
                  )}
                </div>
                {!blocked && !availabilityError ? (
                  <Link
                    href={`${base}/checkout?from=${from}&to=${to}&unit_id=${unit.id}`}
                    className="btn"
                  >
                    {t("book")}
                  </Link>
                ) : null}
              </li>
            );
          })}
        </ul>

        {unitsRes.results.length === 0 ? <p className="text-muted">{t("noUnits")}</p> : null}
      </div>
    </BookingShell>
  );
}
