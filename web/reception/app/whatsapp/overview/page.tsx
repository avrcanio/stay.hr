"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ReceptionNav } from "@/app/_components/ReceptionNav";

type IntegrationStatus = {
  connected: boolean;
  provider: string;
  embedded_signup_supported: boolean;
  business_verified: boolean | null;
  display_name: string;
  phone_number: string;
  waba_id: string;
  quality_rating: string;
  messaging_limit: string | number | null;
  fetched_at: string;
};

export default function WhatsAppOverviewPage() {
  const t = useTranslations("whatsapp.overview");
  const tc = useTranslations("common");
  const [tenantName, setTenantName] = useState("");
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/stay/reception/whatsapp/integration/");
      if (!res.ok) throw new Error(t("loadFailed"));
      setStatus((await res.json()) as IntegrationStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetch("/api/stay/app/config")
      .then((res) => (res.ok ? res.json() : null))
      .then((config) => {
        if (config?.tenant?.name) setTenantName(config.tenant.name);
      })
      .catch(() => undefined);
    void load();
  }, [load]);

  return (
    <div className="min-h-screen bg-stay-surface">
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-4xl px-4 py-6">
        <h1 className="mb-4 text-2xl font-bold text-stay-navy">{t("title")}</h1>
        {loading ? <p className="text-stay-muted">{tc("loading")}</p> : null}
        {error ? <p className="text-red-600">{error}</p> : null}
        {status ? (
          <section className="card space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                  status.connected ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-700"
                }`}
              >
                {status.connected ? t("connected") : t("notConnected")}
              </span>
              {status.quality_rating ? (
                <span className="rounded-full bg-stay-blue-light px-2 py-0.5 text-xs font-medium text-stay-blue">
                  {t("quality")}: {status.quality_rating}
                </span>
              ) : null}
            </div>
            <p>
              <span className="font-medium">{t("phone")}:</span>{" "}
              {status.phone_number || "—"}
            </p>
            <p>
              <span className="font-medium">{t("provider")}:</span> {status.provider || "—"}
            </p>
            <p>
              <span className="font-medium">{t("waba")}:</span> {status.waba_id || "—"}
            </p>
            {status.messaging_limit != null ? (
              <p>
                <span className="font-medium">{t("messagingLimit")}:</span>{" "}
                {String(status.messaging_limit)}
              </p>
            ) : null}
            {status.business_verified === false ? (
              <p className="text-amber-700">{t("businessNotVerified")}</p>
            ) : null}
            {status.embedded_signup_supported ? (
              <p className="text-sm text-stay-muted">{t("connectHint")}</p>
            ) : null}
            <button type="button" className="btn-secondary" onClick={() => void load()}>
              {tc("refresh")}
            </button>
          </section>
        ) : null}
      </main>
    </div>
  );
}
