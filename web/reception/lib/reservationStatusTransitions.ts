import type { ReservationStatus } from "@/lib/types";

const ALLOWED_STATUS_TRANSITIONS: Record<ReservationStatus, ReservationStatus[]> = {
  expected: ["checked_in", "canceled", "no_show"],
  checked_in: ["checked_out"],
  checked_out: [],
  canceled: [],
  no_show: [],
  pending: [],
  refused: [],
};

export type StatusActionKey = "checkInAction" | "checkOutAction" | "cancel" | "noShowAction";

const STATUS_ACTION_KEYS: Partial<Record<ReservationStatus, StatusActionKey>> = {
  checked_in: "checkInAction",
  checked_out: "checkOutAction",
  canceled: "cancel",
  no_show: "noShowAction",
};

export function allowedNextStatuses(current: ReservationStatus): ReservationStatus[] {
  return ALLOWED_STATUS_TRANSITIONS[current] ?? [];
}

export function statusActionKey(nextStatus: ReservationStatus): StatusActionKey | null {
  return STATUS_ACTION_KEYS[nextStatus] ?? null;
}

export function statusSuccessKey(nextStatus: ReservationStatus): string | null {
  if (nextStatus === "checked_in") return "checkInSuccess";
  if (nextStatus === "checked_out") return "checkOutSuccess";
  if (nextStatus === "canceled") return "cancelSuccess";
  if (nextStatus === "no_show") return "noShowSuccess";
  return null;
}

export function statusConfirmKey(nextStatus: ReservationStatus): string | null {
  if (nextStatus === "checked_in") return "checkInConfirm";
  if (nextStatus === "checked_out") return "checkOutConfirm";
  if (nextStatus === "canceled") return "cancelConfirm";
  if (nextStatus === "no_show") return "noShowConfirm";
  return null;
}
