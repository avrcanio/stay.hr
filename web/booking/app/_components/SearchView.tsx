import Link from "next/link";
import type { SiteContext } from "@/lib/types";
import { propertyBasePath } from "@/lib/site-context";
import { addDaysIso, nightsBetween, todayIso } from "@/lib/utils";
import { stayFetch } from "@/lib/stay-server";
import type { AvailabilityResponse, PublicUnit } from "@/lib/types";
import { BookingShell } from "@/app/_components/BookingShell";

type Props = {
  ctx: SiteContext;
  host: string;
  propertySlug: string;
  checkIn?: string;
  checkOut?: string;
};

export async function SearchView({ ctx, host, propertySlug, checkIn, checkOut }: Props) {
  const from = checkIn || todayIso();
  const to = checkOut || addDaysIso(from, 2);
  const base = propertyBasePath(ctx, propertySlug);

  const unitsRes = await stayFetch<{ results: PublicUnit[] }>(
    `/api/v1/public/units?property=${encodeURIComponent(propertySlug)}`,
    { host },
  );

  let availability: AvailabilityResponse | null = null;
  try {
    availability = await stayFetch<AvailabilityResponse>(
      `/api/v1/public/availability?from=${from}&to=${to}&property=${encodeURIComponent(propertySlug)}`,
      { host },
    );
  } catch {
    availability = null;
  }

  const nights = nightsBetween(from, to);
  const propertyName = ctx.property?.name || propertySlug;

  return (
    <BookingShell ctx={ctx} propertySlug={propertySlug}>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Dostupnost — {propertyName}</h1>
          <p className="text-sm text-stone-500">
            {from} → {to} ({nights} noći)
          </p>
        </div>

        <form method="get" className="card flex flex-wrap items-end gap-4">
          <div>
            <label className="label" htmlFor="from">
              Dolazak
            </label>
            <input id="from" name="from" type="date" defaultValue={from} className="input mt-1" />
          </div>
          <div>
            <label className="label" htmlFor="to">
              Odlazak
            </label>
            <input id="to" name="to" type="date" defaultValue={to} className="input mt-1" />
          </div>
          <button type="submit" className="btn">
            Ažuriraj
          </button>
        </form>

        <ul className="space-y-3">
          {unitsRes.results.map((unit) => {
            const avail = availability?.units.find((u) => u.unit_id === unit.id);
            const blocked = (avail?.blocked_periods?.length ?? 0) > 0;
            return (
              <li key={unit.id} className="card flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-semibold">{unit.code} — {unit.name}</div>
                  <div className="text-sm text-stone-500">
                    Do {unit.capacity_max_guests} gostiju
                  </div>
                  {blocked ? (
                    <div className="text-xs text-amber-700">Djelomično zauzeto u periodu</div>
                  ) : (
                    <div className="text-xs text-teal-700">Dostupno</div>
                  )}
                </div>
                <Link
                  href={`${base}/checkout?from=${from}&to=${to}`}
                  className="btn"
                >
                  Rezerviraj
                </Link>
              </li>
            );
          })}
        </ul>

        {unitsRes.results.length === 0 ? (
          <p className="text-stone-500">Nema aktivnih jedinica za ovaj objekt.</p>
        ) : null}
      </div>
    </BookingShell>
  );
}
