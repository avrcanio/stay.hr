"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

type PortalStep = {
  caption?: string;
  image_url?: string;
  image_rel?: string;
  index?: string;
};

type PortalSectionBlock = Record<string, unknown> & {
  text?: string;
  message?: string;
  check_in?: string;
  check_out?: string;
  ssid?: string;
  password?: string;
  maps_url?: string;
  image_url?: string;
  phone?: string;
  whatsapp_url?: string;
  hours?: string;
  room_code?: string;
  key_label?: string;
  steps?: PortalStep[];
};

type PortalContent = Record<string, PortalSectionBlock>;

type PortalPayload = {
  property_name: string;
  language: string;
  sections: string[];
  content: PortalContent;
  branding?: Record<string, unknown>;
  self_service_active?: boolean;
  status?: string;
  opens_at?: string;
};

type Props = {
  token: string;
  lang?: string | null;
};

const SECTION_I18N: Record<string, string> = {
  welcome: "welcome",
  arrival: "arrival",
  key_guide: "keyGuide",
  parking: "parking",
  wifi: "wifi",
  breakfast: "breakfast",
  contact: "contact",
};

export function GuestPortalView({ token, lang }: Props) {
  const t = useTranslations("guestPortal");
  const [loading, setLoading] = useState(true);
  const [gateStatus, setGateStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<PortalPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const qs = lang ? `?lang=${encodeURIComponent(lang)}` : "";
        const res = await fetch(`/api/g/${encodeURIComponent(token)}${qs}`);
        const data = (await res.json()) as PortalPayload;
        if (cancelled) return;
        if (res.status === 403 || res.status === 410) {
          setGateStatus(data.status || "expired");
          setPayload(null);
          return;
        }
        if (!res.ok) {
          setError(t("loadFailed"));
          setPayload(null);
          return;
        }
        setGateStatus(null);
        setPayload(data);
      } catch {
        if (!cancelled) {
          setError(t("loadFailed"));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [token, lang, t]);

  if (loading) {
    return (
      <div className="card text-center">
        <p className="text-muted">{t("loading")}</p>
      </div>
    );
  }

  if (gateStatus === "not_open_yet") {
    return (
      <div className="card space-y-3 text-center">
        <h1 className="text-xl font-bold text-stay-navy">{t("notOpenTitle")}</h1>
        <p className="text-muted">{t("notOpenBody")}</p>
      </div>
    );
  }

  if (gateStatus === "expired" || gateStatus === "revoked") {
    return (
      <div className="card space-y-3 text-center">
        <h1 className="text-xl font-bold text-stay-navy">{t("expiredTitle")}</h1>
        <p className="text-muted">{t("expiredBody")}</p>
      </div>
    );
  }

  if (!payload || error) {
    return (
      <div className="card text-center">
        <p className="text-red-600">{error || t("loadFailed")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-stay-navy">{payload.property_name}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </div>

      {payload.sections.map((section) => {
        const block = payload.content[section];
        if (!block) return null;
        const titleKey = SECTION_I18N[section];
        const title = titleKey ? t(`sections.${titleKey}`) : section;

        return (
          <section key={section} className="card space-y-3">
            <h2 className="text-lg font-semibold text-stay-navy">{title}</h2>
            <PortalSectionBody section={section} block={block} token={token} t={t} />
          </section>
        );
      })}
    </div>
  );
}

function PortalSectionBody({
  section,
  block,
  token,
  t,
}: {
  section: string;
  block: PortalSectionBlock;
  token: string;
  t: ReturnType<typeof useTranslations>;
}) {
  if (section === "welcome") {
    return (
      <div className="space-y-2 text-sm text-stay-navy">
        {block.message ? <p className="whitespace-pre-line">{block.message}</p> : null}
        {block.check_in && block.check_out ? (
          <p className="text-muted">
            {block.check_in} → {block.check_out}
          </p>
        ) : null}
      </div>
    );
  }

  if (section === "wifi") {
    return (
      <div className="space-y-2 text-sm">
        {block.ssid ? (
          <p>
            <span className="font-medium">{t("wifiSsid")}:</span> {block.ssid}
          </p>
        ) : null}
        {block.password ? (
          <p>
            <span className="font-medium">{t("wifiPassword")}:</span> {block.password}
          </p>
        ) : null}
        {block.text && !block.ssid ? (
          <p className="whitespace-pre-line text-stay-navy">{block.text}</p>
        ) : null}
      </div>
    );
  }

  if (section === "arrival") {
    return (
      <div className="space-y-3 text-sm">
        {block.text ? <p className="whitespace-pre-line text-stay-navy">{block.text}</p> : null}
        {block.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={block.image_url.startsWith("/") ? block.image_url : `/api/g/${token}/entrance`}
            alt={t("entranceImageAlt")}
            className="mx-auto max-h-[28rem] w-auto max-w-full rounded-xl border border-stay-border object-contain"
          />
        ) : null}
        {block.maps_url ? (
          <a
            href={block.maps_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex text-stay-blue underline"
          >
            {t("openMaps")}
          </a>
        ) : null}
      </div>
    );
  }

  if (section === "key_guide") {
    const steps = Array.isArray(block.steps) ? block.steps : [];
    return (
      <div className="space-y-4 text-sm text-stay-navy">
        {block.room_code || block.key_label ? (
          <p className="text-muted">
            {block.room_code ? (
              <span>
                {t("room")}: {block.room_code}
              </span>
            ) : null}
            {block.room_code && block.key_label ? " · " : null}
            {block.key_label ? (
              <span>
                {t("keyLabel")}: {block.key_label}
              </span>
            ) : null}
          </p>
        ) : null}
        {steps.map((step, idx) => (
          <div key={step.index || String(idx)} className="space-y-2">
            {step.caption ? <p className="whitespace-pre-line">{step.caption}</p> : null}
            {step.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={
                  step.image_url.startsWith("/")
                    ? step.image_url
                    : `/api/g/${token}/steps/${step.index || idx}`
                }
                alt={step.caption || t("keyGuideStepAlt", { step: idx + 1 })}
                className="mx-auto max-h-[28rem] w-auto max-w-full rounded-xl border border-stay-border object-contain"
              />
            ) : null}
          </div>
        ))}
      </div>
    );
  }

  if (section === "contact") {
    return (
      <div className="space-y-2 text-sm">
        {block.phone ? (
          <p>
            <span className="font-medium">{t("phone")}:</span>{" "}
            <a href={`tel:${block.phone}`} className="text-stay-blue underline">
              {block.phone}
            </a>
          </p>
        ) : null}
        {block.whatsapp_url ? (
          <a
            href={block.whatsapp_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex text-stay-blue underline"
          >
            {t("whatsapp")}
          </a>
        ) : null}
      </div>
    );
  }

  if (section === "breakfast") {
    return (
      <div className="space-y-2 text-sm text-stay-navy">
        {block.text ? <p className="whitespace-pre-line">{block.text}</p> : null}
        {block.hours ? (
          <p className="text-muted">
            {t("hours")}: {block.hours}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="text-sm text-stay-navy">
      {block.text ? <p className="whitespace-pre-line">{block.text}</p> : null}
    </div>
  );
}
