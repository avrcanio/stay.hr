"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

type Props = {
  open: boolean;
  onClose: () => void;
  onConfirm: (email: string) => Promise<void>;
};

export function InvoiceEmailModal({ open, onClose, onConfirm }: Props) {
  const t = useTranslations("reservation");
  const tc = useTranslations("common");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  function handleClose() {
    if (busy) return;
    setError("");
    onClose();
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = email.trim();
    if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setError(t("invoiceEmailInvalid"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onConfirm(trimmed);
      setEmail("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : tc("error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        className="card flex w-full max-w-md flex-col overflow-visible"
        role="dialog"
        aria-modal="true"
        aria-labelledby="invoice-email-title"
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 id="invoice-email-title" className="font-semibold text-stay-navy">
            {t("invoiceEmailModalTitle")}
          </h2>
          <button
            type="button"
            className="btn-ghost px-2"
            onClick={handleClose}
            disabled={busy}
            aria-label={tc("close")}
          >
            ×
          </button>
        </div>

        <form className="space-y-3 px-4 py-4" onSubmit={(event) => void handleSubmit(event)}>
          <p className="text-sm text-muted">{t("invoiceNoEmailHint")}</p>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">{t("invoiceEmailLabel")}</span>
            <input
              type="email"
              className="input w-full"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoFocus
              disabled={busy}
            />
          </label>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" className="btn-ghost" onClick={handleClose} disabled={busy}>
              {t("moveDatesCancel")}
            </button>
            <button type="submit" className="btn btn-sm" disabled={busy}>
              {busy ? tc("loading") : t("invoiceEmailModalConfirm")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
