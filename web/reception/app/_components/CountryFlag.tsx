"use client";

import { useTranslations } from "next-intl";
import { flagClass } from "@/lib/utils";

type Props = {
  iso2?: string | null;
  title?: string;
  size?: "sm" | "md";
  className?: string;
};

const sizeClass: Record<NonNullable<Props["size"]>, string> = {
  sm: "text-base leading-none",
  md: "text-xl leading-none",
};

export function CountryFlag({ iso2, title, size = "sm", className = "" }: Props) {
  const t = useTranslations("common");
  const cc = flagClass(iso2);
  if (!cc) {
    return (
      <span
        className={`inline-block h-3.5 w-5 rounded-sm bg-stay-border ${className}`}
        title={title || t("unknownCountry")}
        aria-hidden="true"
      />
    );
  }

  const label = title || cc.toUpperCase();

  return (
    <span
      className={`fi fi-${cc} fis inline-block rounded-sm shadow-sm ${sizeClass[size]} ${className}`}
      title={label}
      aria-label={label}
      role="img"
    />
  );
}
