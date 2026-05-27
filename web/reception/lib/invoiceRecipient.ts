import type { GuestLite, ReservationDetail } from "@/lib/types";

export function invoiceRecipientEmail(
  reservation: Pick<ReservationDetail, "booker_email" | "guests">,
): string {
  const booker = (reservation.booker_email || "").trim();
  if (booker) return booker;
  const primary = reservation.guests?.find((guest: GuestLite) => guest.is_primary);
  return (primary?.email || "").trim();
}
