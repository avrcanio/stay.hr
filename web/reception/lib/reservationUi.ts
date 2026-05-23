import type { ReservationStatus } from "@/lib/types";

export const statusClass: Record<string, string> = {
  expected: "badge-expected",
  checked_in: "badge-checked_in",
  checked_out: "badge-checked_out",
  canceled: "badge-canceled",
  pending: "badge-expected",
  refused: "badge-canceled",
};

export const statusBarClass: Record<string, string> = {
  expected: "bg-amber-200 border-amber-400 text-amber-950",
  checked_in: "bg-emerald-200 border-emerald-500 text-emerald-950",
  checked_out: "bg-slate-200 border-slate-400 text-slate-800",
  canceled: "bg-red-100 border-red-300 text-red-900",
  pending: "bg-amber-200 border-amber-400 text-amber-950",
  refused: "bg-red-100 border-red-300 text-red-900",
};

export function reservationStatusClass(status: string): string {
  return statusClass[status] || "badge-expected";
}

export function reservationStatusBarClass(status: string): string {
  return statusBarClass[status] || statusBarClass.expected;
}

export type { ReservationStatus };
