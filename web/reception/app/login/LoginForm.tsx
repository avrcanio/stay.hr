"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { useTranslations } from "next-intl";
import { StayLogo } from "@/app/_components/StayLogo";
import type { LoginErrorKey } from "@/lib/login-errors";
import type { TenantOption } from "@/lib/types";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useTranslations("login");
  const te = useTranslations("errors");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [tenants, setTenants] = useState<TenantOption[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function translateError(data: { errorKey?: LoginErrorKey; detail?: string; error?: string }) {
    if (data.errorKey) {
      if (data.errorKey === "loginFailedDetail" && data.detail) {
        return te("loginFailedDetail", { detail: data.detail });
      }
      return te(data.errorKey);
    }
    return data.error || t("failed");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const payload: { username: string; password: string; tenant_id?: number } = {
        username: username.trim(),
        password,
      };
      if (tenantId) {
        payload.tenant_id = Number(tenantId);
      }

      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));

      if (res.status === 409 && data.requires_tenant && Array.isArray(data.tenants)) {
        setTenants(data.tenants);
        if (data.tenants.length === 1) {
          setTenantId(String(data.tenants[0].id));
        }
        setError(t("selectTenantRetry"));
        return;
      }

      if (!res.ok) {
        throw new Error(translateError(data));
      }

      const next = searchParams.get("next") || "/";
      router.push(next);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : te("loginFailed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-md">
      <form onSubmit={onSubmit} className="card space-y-5 p-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <StayLogo href={null} />
          <div>
            <h1 className="text-xl font-bold text-stay-navy">{t("title")}</h1>
            <p className="mt-1 text-sm text-muted">{t("subtitle")}</p>
          </div>
        </div>
        {error ? <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
        <div>
          <label className="label" htmlFor="username">
            {t("username")}
          </label>
          <input
            id="username"
            className="input mt-1"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </div>
        <div>
          <label className="label" htmlFor="password">
            {t("password")}
          </label>
          <input
            id="password"
            type="password"
            className="input mt-1"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        {tenants.length > 0 ? (
          <div>
            <label className="label" htmlFor="tenant">
              {t("tenant")}
            </label>
            <select
              id="tenant"
              className="input mt-1"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              required
            >
              <option value="">{t("tenantPlaceholder")}</option>
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <button type="submit" className="btn w-full" disabled={loading}>
          {loading ? t("submitting") : t("submit")}
        </button>
      </form>
    </div>
  );
}
