import { addDaysIso } from "@/lib/utils";

export type UnitAvailabilityResponse = {
  unit_id: number;
  from: string;
  to: string;
  blocked_nights: string[];
};

export async function fetchUnitBlockedNights(
  unitId: number,
  from: string,
  to: string,
  excludeReservationId?: number,
): Promise<Set<string>> {
  const params = new URLSearchParams({ from, to });
  if (excludeReservationId !== undefined) {
    params.set("exclude_reservation_id", String(excludeReservationId));
  }
  const res = await fetch(`/api/stay/reception/units/${unitId}/availability/?${params}`);
  if (!res.ok) {
    throw new Error("Failed to load unit availability");
  }
  const data = (await res.json()) as UnitAvailabilityResponse;
  return new Set(data.blocked_nights);
}

export function isCheckInAllowed(night: string, blocked: Set<string>, today: string): boolean {
  return night >= today && !blocked.has(night);
}

function isNightInStay(night: string, stayCheckIn: string, stayCheckOut: string): boolean {
  return night >= stayCheckIn && night < stayCheckOut;
}

export function isMoveCheckInAllowed(
  night: string,
  blocked: Set<string>,
  today: string,
  stayCheckIn: string,
  stayCheckOut: string,
): boolean {
  if (isNightInStay(night, stayCheckIn, stayCheckOut)) {
    return true;
  }
  return isCheckInAllowed(night, blocked, today);
}

export function isCheckOutAllowed(
  checkIn: string,
  checkOut: string,
  blocked: Set<string>,
): boolean {
  if (!checkIn || checkOut <= checkIn) return false;
  let night = checkIn;
  while (night < checkOut) {
    if (blocked.has(night)) return false;
    night = addDaysIso(night, 1);
  }
  return true;
}

export function isMoveCheckOutAllowed(
  checkIn: string,
  checkOut: string,
  blocked: Set<string>,
  stayCheckIn: string,
  stayCheckOut: string,
): boolean {
  if (!checkIn || checkOut <= checkIn) return false;
  let night = checkIn;
  while (night < checkOut) {
    if (!isNightInStay(night, stayCheckIn, stayCheckOut) && blocked.has(night)) {
      return false;
    }
    night = addDaysIso(night, 1);
  }
  return true;
}

export function rangeHasBlockedNight(
  checkIn: string,
  checkOut: string,
  blocked: Set<string>,
): boolean {
  return !isCheckOutAllowed(checkIn, checkOut, blocked);
}
