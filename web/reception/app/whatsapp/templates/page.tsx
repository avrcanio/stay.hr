"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ReceptionNav } from "@/app/_components/ReceptionNav";

type TemplateRow = {
  id?: string;
  name: string;
  language: string;
  category?: string;
  status: string;
};

export default function WhatsAppTemplatesPage() {
  const t = useTranslations("whatsapp.templates");
  const tc = useTranslations("common");
  const [tenantName, setTenantName] = useState("");
  const [templates, setTemplates] = useState<TemplateRow[]>([]);
  const [syncedAt, setSyncedAt] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("hr");
  const [bodyText, setBodyText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (live = false) => {
    setLoading(true);
    setError("");
    try {
      const qs = live ? "?live=1" : "";
      const res = await fetch(`/api/stay/reception/whatsapp/templates/${qs}`);
      if (!res.ok) throw new Error(t("loadFailed"));
      const data = (await res.json()) as { templates: TemplateRow[]; synced_at?: string };
      setTemplates(data.templates ?? []);
      setSyncedAt(data.synced_at ?? "");
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

  async function handleSync() {
    setBusy(true);
    setMessage("");
    try {
      const res = await fetch("/api/stay/reception/whatsapp/templates/sync/", { method: "POST" });
      if (!res.ok) throw new Error(t("syncFailed"));
      const data = (await res.json()) as { templates: TemplateRow[]; synced_at?: string };
      setTemplates(data.templates ?? []);
      setSyncedAt(data.synced_at ?? "");
      setMessage(t("syncSuccess"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("syncFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const res = await fetch("/api/stay/reception/whatsapp/templates/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, language, body_text: bodyText, category: "MARKETING" }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail || t("createFailed"));
      }
      setMessage(t("createSuccess"));
      setName("");
      setBodyText("");
      await handleSync();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("createFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-stay-surface">
      <ReceptionNav tenantName={tenantName} />
      <main className="mx-auto max-w-5xl px-4 py-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-bold text-stay-navy">{t("title")}</h1>
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => void handleSync()}>
            {t("sync")}
          </button>
        </div>
        {syncedAt ? (
          <p className="mb-3 text-sm text-stay-muted">
            {t("syncedAt")}: {new Date(syncedAt).toLocaleString()}
          </p>
        ) : null}
        {loading ? <p className="text-stay-muted">{tc("loading")}</p> : null}
        {error ? <p className="mb-3 text-red-600">{error}</p> : null}
        {message ? <p className="mb-3 text-green-700">{message}</p> : null}

        <section className="card mb-6 overflow-x-auto p-4">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-stay-border text-stay-muted">
                <th className="py-2 pr-3">{t("colName")}</th>
                <th className="py-2 pr-3">{t("colLanguage")}</th>
                <th className="py-2 pr-3">{t("colCategory")}</th>
                <th className="py-2">{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((row) => (
                <tr key={`${row.name}-${row.language}`} className="border-b border-stay-border/60">
                  <td className="py-2 pr-3 font-medium">{row.name}</td>
                  <td className="py-2 pr-3">{row.language}</td>
                  <td className="py-2 pr-3">{row.category || "—"}</td>
                  <td className="py-2">{row.status}</td>
                </tr>
              ))}
              {!loading && templates.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-4 text-stay-muted">
                    {t("empty")}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>

        <section className="card p-4">
          <h2 className="mb-3 text-lg font-semibold text-stay-navy">{t("createTitle")}</h2>
          <form className="space-y-3" onSubmit={(e) => void handleCreate(e)}>
            <label className="block">
              <span className="text-sm font-medium">{t("fieldName")}</span>
              <input
                className="input mt-1 w-full"
                value={name}
                onChange={(e) => setName(e.target.value)}
                pattern="[a-z0-9_]+"
                required
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium">{t("fieldLanguage")}</span>
              <input
                className="input mt-1 w-full"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                required
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium">{t("fieldBody")}</span>
              <textarea
                className="input mt-1 min-h-28 w-full"
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
                required
              />
            </label>
            <button type="submit" className="btn-primary" disabled={busy}>
              {t("createAction")}
            </button>
          </form>
        </section>
      </main>
    </div>
  );
}
