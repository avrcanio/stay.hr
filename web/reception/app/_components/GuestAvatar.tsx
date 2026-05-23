"use client";

import { useState } from "react";

type Props = {
  reservationId: number;
  guestId: number;
  name: string;
  size?: "sm" | "lg";
  className?: string;
};

const sizeClass: Record<NonNullable<Props["size"]>, string> = {
  sm: "h-8 w-8 text-xs",
  lg: "h-16 w-16 text-lg",
};

function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
}

export function guestFacePhotoPath(reservationId: number, guestId: number): string {
  return `/api/stay/reception/reservations/${reservationId}/guests/${guestId}/face-photo/`;
}

export function GuestAvatar({
  reservationId,
  guestId,
  name,
  size = "sm",
  className = "",
}: Props) {
  const [failed, setFailed] = useState(false);
  const initials = initialsFromName(name);
  const sizeStyles = sizeClass[size];

  if (failed) {
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-full bg-stay-blue-light font-semibold text-stay-blue ${sizeStyles} ${className}`}
        aria-hidden="true"
      >
        {initials}
      </span>
    );
  }

  return (
    <img
      src={guestFacePhotoPath(reservationId, guestId)}
      alt={name}
      className={`shrink-0 rounded-full bg-stay-border object-cover ${sizeStyles} ${className}`}
      onError={() => setFailed(true)}
    />
  );
}
