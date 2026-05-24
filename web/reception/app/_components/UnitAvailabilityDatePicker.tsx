"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { daysInMonth } from "@/lib/calendarLayout";
import { useMonthLabel, weekdayLabelForLocale } from "@/lib/i18n-ui";
import { addMonthsIso, startOfMonthIso, todayIso } from "@/lib/utils";

type Props = {
  label: string;
  value: string;
  onChange: (iso: string) => void;
  isDateDisabled: (iso: string) => boolean;
  disabled?: boolean;
  placeholder?: string;
  /** When value is empty, calendar opens on this date's month (e.g. check-in for checkout picker). */
  anchorDate?: string;
};

const WEEKDAY_ORDER = [1, 2, 3, 4, 5, 6, 0];

function formatDisplayDate(iso: string, locale: string): string {
  if (!iso) return "";
  const d = new Date(`${iso}T12:00:00Z`);
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(d);
}

export function UnitAvailabilityDatePicker({
  label,
  value,
  onChange,
  isDateDisabled,
  disabled = false,
  placeholder = "",
  anchorDate = "",
}: Props) {
  const t = useTranslations("newReservation");
  const locale = useLocale();
  const monthLabel = useMonthLabel();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => startOfMonthIso(value || todayIso()));

  useEffect(() => {
    if (value) {
      setMonth(startOfMonthIso(value));
    } else if (anchorDate) {
      setMonth(startOfMonthIso(anchorDate));
    }
  }, [value, anchorDate]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const days = daysInMonth(month);
  const leadingBlanks = days.length > 0 ? days[0].weekday : 0;
  const today = todayIso();

  function selectDate(iso: string) {
    if (isDateDisabled(iso)) return;
    onChange(iso);
    setOpen(false);
  }

  return (
    <div ref={rootRef} className="relative block text-sm">
      <span className="label">{label}</span>
      <button
        type="button"
        className="input mt-1 flex w-full items-center justify-between text-left"
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => {
          if (disabled) return;
          if (!value && anchorDate) {
            setMonth(startOfMonthIso(anchorDate));
          }
          setOpen((current) => !current);
        }}
      >
        <span className={value ? "text-stay-navy" : "text-stay-muted"}>
          {value ? formatDisplayDate(value, locale) : placeholder || t("datePlaceholder")}
        </span>
        <span className="text-stay-muted" aria-hidden>
          ▾
        </span>
      </button>

      {open ? (
        <div
          id={listId}
          role="dialog"
          aria-label={label}
          className="absolute z-[60] mt-1 w-full min-w-[16rem] rounded-lg border border-stay-border bg-white p-3 shadow-lg"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <button
              type="button"
              className="rounded px-2 py-1 text-sm text-stay-navy hover:bg-slate-100"
              aria-label={t("prevMonth")}
              onClick={() => setMonth((current) => addMonthsIso(current, -1))}
            >
              ‹
            </button>
            <span className="text-sm font-semibold text-stay-navy">{monthLabel(month)}</span>
            <button
              type="button"
              className="rounded px-2 py-1 text-sm text-stay-navy hover:bg-slate-100"
              aria-label={t("nextMonth")}
              onClick={() => setMonth((current) => addMonthsIso(current, 1))}
            >
              ›
            </button>
          </div>

          <div className="mb-1 grid grid-cols-7 gap-0.5 text-center text-[10px] font-medium uppercase text-stay-muted">
            {WEEKDAY_ORDER.map((weekday) => (
              <div key={weekday} className="py-1">
                {weekdayLabelForLocale(locale, weekday)}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-0.5">
            {Array.from({ length: leadingBlanks }).map((_, index) => (
              <div key={`blank-${index}`} className="h-9" />
            ))}
            {days.map((day) => {
              const unavailable = isDateDisabled(day.iso);
              const selected = value === day.iso;
              const isToday = day.iso === today;
              return (
                <button
                  key={day.iso}
                  type="button"
                  disabled={unavailable}
                  onClick={() => selectDate(day.iso)}
                  className={`h-9 rounded text-sm ${
                    unavailable
                      ? "cursor-not-allowed bg-slate-50 text-slate-300 line-through"
                      : selected
                        ? "bg-stay-blue font-semibold text-white"
                        : isToday
                          ? "bg-stay-blue-light font-medium text-stay-blue hover:bg-stay-blue/10"
                          : "text-stay-navy hover:bg-slate-100"
                  }`}
                >
                  {day.dayOfMonth}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
