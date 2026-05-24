"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { CountryFlag } from "@/app/_components/CountryFlag";
import { GuestAvatar } from "@/app/_components/GuestAvatar";
import type { GuestLite } from "@/lib/types";

type DetailRow = {
  label: string;
  value: string | null | undefined;
  fullWidth?: boolean;
  isError?: boolean;
};

type Props = {
  reservationId: number;
  guests: GuestLite[];
};

export function GuestList({ reservationId, guests }: Props) {
  const t = useTranslations("guest");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  function evisitorStatusLabel(status: string): string {
    const map: Record<string, string> = {
      pending: t("evisitorPending"),
      submitted: t("evisitorSubmitted"),
      failed: t("evisitorFailed"),
      complete: t("evisitorComplete"),
    };
    return map[status] || status || "—";
  }

  function sexLabel(sex: string): string {
    const value = sex.trim().toUpperCase();
    if (value === "M") return t("sexMale");
    if (value === "F") return t("sexFemale");
    return sex;
  }

  function guestDetailRows(guest: GuestLite): DetailRow[] {
    const rows: DetailRow[] = [
      { label: t("email"), value: guest.email },
      { label: t("phone"), value: guest.phone },
      { label: t("dateOfBirth"), value: guest.date_of_birth },
      { label: t("sex"), value: guest.sex ? sexLabel(guest.sex) : "" },
      { label: t("documentType"), value: guest.document_type },
      { label: t("documentNumber"), value: guest.document_number },
      { label: t("dateOfIssue"), value: guest.date_of_issue },
      { label: t("dateOfExpiry"), value: guest.date_of_expiry },
      { label: t("issuingAuthority"), value: guest.issuing_authority },
      { label: t("personalId"), value: guest.personal_id_number },
      { label: t("address"), value: guest.address, fullWidth: true },
      { label: t("evisitor"), value: evisitorStatusLabel(guest.evisitor_status) },
    ];

    if (guest.evisitor_error) {
      rows.push({
        label: t("evisitorError"),
        value: guest.evisitor_error,
        fullWidth: true,
        isError: true,
      });
    }

    return rows.filter((row) => row.value?.trim());
  }

  function toggleGuest(id: number) {
    setExpandedId((current) => (current === id ? null : id));
  }

  return (
    <ul className="divide-y divide-stay-border rounded-xl border border-stay-border">
      {guests.map((guest) => {
        const expanded = expandedId === guest.id;
        const panelId = `guest-details-${guest.id}`;
        const fullName = `${guest.first_name} ${guest.last_name}`.trim();
        const detailRows = guestDetailRows(guest);

        return (
          <li key={guest.id}>
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-sm transition hover:bg-slate-50"
              onClick={() => toggleGuest(guest.id)}
              aria-expanded={expanded}
              aria-controls={panelId}
            >
              <span className="flex min-w-0 items-center gap-2">
                <GuestAvatar
                  reservationId={reservationId}
                  guestId={guest.id}
                  name={fullName}
                  facePhotoUrl={guest.face_photo_url}
                  size="sm"
                />
                <CountryFlag iso2={guest.nationality} />
                <span className="truncate">
                  {fullName}
                  {guest.is_primary ? <span className="text-muted"> · {t("primary")}</span> : null}
                </span>
              </span>
              <span className="shrink-0 text-muted" aria-hidden="true">
                {expanded ? "▾" : "▸"}
              </span>
            </button>

            {expanded ? (
              <div id={panelId} className="border-t border-stay-border bg-slate-50/80 px-3 py-3">
                <div className="mb-3 flex items-center gap-3">
                  <GuestAvatar
                    reservationId={reservationId}
                    guestId={guest.id}
                    name={fullName}
                    facePhotoUrl={guest.face_photo_url}
                    size="lg"
                  />
                  <div className="min-w-0">
                    <p className="font-semibold text-stay-navy">{fullName}</p>
                    <p className="flex items-center gap-1.5 text-sm text-muted">
                      <CountryFlag iso2={guest.nationality} />
                      {guest.is_primary ? ` · ${t("primary")}` : null}
                    </p>
                  </div>
                </div>

                {detailRows.length > 0 ? (
                  <dl className="grid gap-2 text-sm sm:grid-cols-2">
                    {detailRows.map((row) => (
                      <div key={row.label} className={row.fullWidth ? "sm:col-span-2" : undefined}>
                        <dt className="text-muted">{row.label}</dt>
                        <dd className={`font-medium ${row.isError ? "text-red-700" : ""}`}>
                          {row.value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="text-sm text-muted">{t("noExtraData")}</p>
                )}
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
