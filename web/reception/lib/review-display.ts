import type { ChannexReview } from "@/lib/types";

/** Prefer localized guest review text when it differs from the OTA original. */
export function reviewDisplayContent(review: ChannexReview): string {
  const original = (review.content || "").trim();
  const localized = (review.content_localized || "").trim();
  if (localized && localized !== original) {
    return review.content_localized!;
  }
  if (review.content_is_translated && localized) {
    return localized;
  }
  return review.content || "";
}

export function reviewHasTranslation(review: ChannexReview): boolean {
  const original = (review.content || "").trim();
  const localized = (review.content_localized || "").trim();
  return Boolean(localized && localized !== original);
}
