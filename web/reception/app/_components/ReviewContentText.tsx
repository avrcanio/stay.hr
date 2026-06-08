"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import type { ChannexReview } from "@/lib/types";
import { reviewDisplayContent, reviewHasTranslation } from "@/lib/review-display";

type Props = {
  review: ChannexReview;
  className?: string;
};

export function ReviewContentText({ review, className = "text-sm" }: Props) {
  const t = useTranslations("guestReviews");
  const [showOriginal, setShowOriginal] = useState(false);
  const hasTranslation = reviewHasTranslation(review);

  const displayText = !showOriginal && hasTranslation ? reviewDisplayContent(review) : review.content;

  if (!displayText?.trim()) {
    if (review.overall_score != null) {
      return <p className={`text-muted ${className}`}>{t("scoreOnlyEmpty")}</p>;
    }
    return <p className={`text-muted ${className}`}>{t("noContentYet")}</p>;
  }

  return (
    <div className="space-y-1">
      <p className={`whitespace-pre-wrap ${className}`}>{displayText}</p>
      {hasTranslation ? (
        <button
          type="button"
          className="text-xs font-medium text-stay-blue hover:underline"
          onClick={() => setShowOriginal((value) => !value)}
        >
          {showOriginal ? t("showTranslation") : t("showOriginal")}
        </button>
      ) : null}
      {hasTranslation && !showOriginal ? (
        <p className="text-xs text-muted">{t("translatedLabel")}</p>
      ) : null}
    </div>
  );
}
