export const RECEPTION_TOKEN_COOKIE = "stay_device_token";

export type ReservationStatus = "expected" | "checked_in" | "checked_out" | "canceled" | "pending";

export type Reservation = {
  id: number;
  external_id: string;
  room_name: string;
  room_codes?: string[];
  check_in_date: string;
  check_out_date: string;
  status: ReservationStatus;
  total_amount: string | null;
  currency: string;
  guests_count: number;
  primary_guest_name: string;
  primary_guest_nationality_iso2: string;
};

export type Room = {
  id: number;
  code: string;
  room_type: number | null;
  room_type_name: string;
  is_active: boolean;
};

export type AppConfig = {
  tenant: { name: string; slug: string };
  properties: Array<{ name: string; slug: string }>;
  feature_flags: Record<string, boolean>;
  branding: Record<string, unknown>;
};

export type ReservationDetail = Reservation & {
  guests: Array<{
    id: number;
    first_name: string;
    last_name: string;
    email: string;
    is_primary: boolean;
    nationality: string;
    evisitor_status: string;
  }>;
  booker_name: string;
  booker_phone: string;
  notes: string;
};

export type CalendarReservation = {
  id: number;
  external_id: string;
  check_in_date: string;
  check_out_date: string;
  status: ReservationStatus;
  room_name: string;
  primary_guest_name: string;
  primary_guest_nationality_iso2: string;
};
