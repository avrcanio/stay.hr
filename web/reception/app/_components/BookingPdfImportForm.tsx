"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import type { BookingPdfImportResult } from "@/lib/types";

type Props = {
  propertySlug?: string;
  reservationId?: number;
  expectedBookingNumber?: string;
  onSuccess: (result: BookingPdfImportResult) => void;
  compact?: boolean;
};

type ImportErrorPayload = {
  code?: string;
  detail?: string;
  file?: string[];
  pdf_booking_number?: string;
  context_booking_number?: string;
};

export function BookingPdfImportForm({
  propertySlug,
  reservationId,
  expectedBookingNumber,
  onSuccess,
  compact = false,
}: Props) {
  const t = useTranslations("reservation");
  const tc = useTranslations("common");
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [activeFilename, setActiveFilename] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function uploadFile(file: File) {
    setUploading(true);
    setActiveFilename(file.name);
    setError("");
    setMessage("");

    try {
      let confirmMismatch = false;

      while (true) {
        const formData = new FormData();
        formData.append("file", file);
        if (propertySlug) {
          formData.append("property_slug", propertySlug);
        }
        if (reservationId) {
          formData.append("reservation_id", String(reservationId));
        }
        if (confirmMismatch) {
          formData.append("confirm_booking_mismatch", "true");
        }

        const res = await fetch("/api/stay/reception/reservations/import-pdf/", {
          method: "POST",
          body: formData,
        });
        const data = (await res.json().catch(() => null)) as
          | (BookingPdfImportResult & ImportErrorPayload)
          | ImportErrorPayload
          | null;

        if (
          res.status === 409 &&
          data?.code === "booking_number_mismatch" &&
          !confirmMismatch
        ) {
          const pdfNumber = data.pdf_booking_number || tc("dash");
          const contextNumber =
            data.context_booking_number || expectedBookingNumber || tc("dash");
          const ok = window.confirm(
            t("importPdfBookingMismatchConfirm", {
              pdf: pdfNumber,
              context: contextNumber,
            }),
          );
          if (!ok) {
            setMessage(t("importPdfCancelled"));
            return;
          }
          confirmMismatch = true;
          continue;
        }

        if (!res.ok) {
          const detail =
            (Array.isArray(data?.file) ? data.file[0] : undefined) ||
            data?.detail ||
            t("importPdfFailed");
          throw new Error(detail);
        }

        setMessage(t("importPdfSuccess"));
        onSuccess(data as BookingPdfImportResult);
        return;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("error"));
    } finally {
      setUploading(false);
      setActiveFilename("");
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    }
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void uploadFile(file);
  }

  function openFilePicker() {
    if (uploading) return;
    inputRef.current?.click();
  }

  return (
    <div className={compact ? "flex flex-wrap items-center gap-2" : "space-y-2"}>
      {!compact ? <h2 className="font-semibold">{t("importPdfTitle")}</h2> : null}

      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        disabled={uploading}
        onChange={handleFileChange}
      />

      <button type="button" className="btn btn-sm" disabled={uploading} onClick={openFilePicker}>
        {uploading ? t("importPdfUploading") : t("importPdf")}
      </button>

      {uploading && activeFilename ? (
        <span className="min-w-0 truncate text-sm text-muted">{activeFilename}</span>
      ) : null}
      {error ? <p className="w-full text-sm text-red-600">{error}</p> : null}
      {message ? <p className="w-full text-sm text-emerald-700">{message}</p> : null}
    </div>
  );
}
