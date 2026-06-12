import fs from "fs";
import path from "path";

/** Filenames under public/product/ */
export const PRODUCT_SCREENSHOT_FILES = {
  bookingSearch: "booking-search.png",
  bookingCheckout: "booking-checkout.png",
  receptionTimeline: "reception-timeline.png",
  receptionCalendar: "reception-calendar.png",
  receptionDetail: "reception-detail.png",
  hospiraTimeline: "hospira-timeline.png",
  hospiraCalendarRooms: "hospira-calendar-rooms.png",
  hospiraCalendarOccupancy: "hospira-calendar-occupancy.png",
  hospiraMessages: "hospira-messages.png",
  hospiraReviews: "hospira-reviews.png",
  hospiraStatisticsMonthly: "hospira-statistics-monthly.png",
  hospiraStatisticsAnnual: "hospira-statistics-annual.png",
} as const;

export type ProductScreenshotId = keyof typeof PRODUCT_SCREENSHOT_FILES;

export function productScreenshotSrc(id: ProductScreenshotId): string | undefined {
  const filename = PRODUCT_SCREENSHOT_FILES[id];
  const filePath = path.join(process.cwd(), "public", "product", filename);
  if (!fs.existsSync(filePath)) {
    return undefined;
  }
  return `/product/${filename}`;
}
