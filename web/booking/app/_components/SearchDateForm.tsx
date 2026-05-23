"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { addDaysIso, nightsBetween } from "@/lib/dates";

type Props = {
  initialFrom: string;
  initialTo: string;
};

function normalizeTo(from: string, to: string): string {
  if (!to || to <= from) {
    return addDaysIso(from, 1);
  }
  return to;
}

export function SearchDateForm({ initialFrom, initialTo }: Props) {
  const t = useTranslations("search");
  const [from, setFrom] = useState(initialFrom);
  const [to, setTo] = useState(() => normalizeTo(initialFrom, initialTo));

  function handleFromChange(newFrom: string) {
    if (!newFrom) return;
    const nights = Math.max(1, nightsBetween(from, to));
    setFrom(newFrom);
    setTo(addDaysIso(newFrom, nights));
  }

  return (
    <form method="get" className="card flex flex-wrap items-end gap-4">
      <div>
        <label className="label" htmlFor="from">
          {t("checkIn")}
        </label>
        <input
          id="from"
          name="from"
          type="date"
          value={from}
          onChange={(e) => handleFromChange(e.target.value)}
          className="input mt-1"
          required
        />
      </div>
      <div>
        <label className="label" htmlFor="to">
          {t("checkOut")}
        </label>
        <input
          id="to"
          name="to"
          type="date"
          value={to}
          min={addDaysIso(from, 1)}
          onChange={(e) => setTo(e.target.value)}
          className="input mt-1"
          required
        />
      </div>
      <button type="submit" className="btn">
        {t("update")}
      </button>
    </form>
  );
}
