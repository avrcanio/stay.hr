import type { ReservationDetail } from "@/lib/types";

export type CheckInBlockedCode = "wrong_date" | "room_occupied" | "no_unit";

const CHECK_IN_BLOCKED_MESSAGE_KEYS: Record<CheckInBlockedCode, string> = {
  wrong_date: "checkInBlockedWrongDate",
  room_occupied: "checkInBlockedRoomOccupied",
  no_unit: "checkInBlockedNoUnit",
};

export function isCheckInActionDisabled(reservation: ReservationDetail): boolean {
  return reservation.status === "expected" && reservation.check_in_allowed === false;
}

export function checkInBlockedMessageKey(
  code: ReservationDetail["check_in_blocked_code"],
): string | null {
  if (!code) return null;
  return CHECK_IN_BLOCKED_MESSAGE_KEYS[code as CheckInBlockedCode] ?? null;
}

export function showCheckInBlockedHint(reservation: ReservationDetail): boolean {
  return isCheckInActionDisabled(reservation);
}
