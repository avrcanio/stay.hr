"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ReceptionNav } from "@/app/_components/ReceptionNav";

type IntegrationStatus = {
  connected: boolean;
  phone_number: string;
  waba_id: string;
  provider: string;
};

export default function WhatsAppSettingsPage() {
  const t = useTranslations("whatsapp.settings");
  const tc = useTranslations("common");
  const [tenantName, setTenantName] = useState("");
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/stay/reception/whatsapp/integration/");
      if (res.ok) setStatus((await res.json()) as IntegrationStatus);
    } finally {
      setLoading(false);
    }
  }, []);

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
        {status ? (
          <section className="card space-y-2 p-4 text-sm">
            <p>
              <span className="font-medium">{t("connected")}:</span>{" "}
              {status.connected ? tc("yes") : tc("no")}
            </p>
            <p>
              <span className="font-medium">{t("phone")}:</span> {status.phone_number || "—"}
            </p>
            <p>
              <span className="font-medium">{t("waba")}:</span> {status.waba_id || "—"}
            </p>
            <p className="text-stay-muted">{t("disconnectHint")}</p>
          </section>
        ) : null}
      </main>
    </div>
  );
}
