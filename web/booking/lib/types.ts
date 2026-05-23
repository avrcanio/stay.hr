export type TenantSummary = {
  id: number;
  name: string;
  slug: string;
  status: string;
  timezone: string;
  default_language: string;
};

export type PropertySummary = {
  id: number;
  name: string;
  slug: string;
  address: string;
  contact: Record<string, unknown>;
  branding: Record<string, unknown>;
  timezone: string;
  language: string;
};

export type SiteContext = {
  tenant: TenantSummary;
  property: PropertySummary | null;
  domain_type: string;
  branding: Record<string, unknown>;
  languages: string[];
  default_language: string;
};

export type PublicUnit = {
  id: number;
  property_slug: string;
  code: string;
  name: string;
  capacity_max_guests: number;
  capacity_adults: number;
  capacity_children: number;
  capacity_infants: number;
  is_active: boolean;
};

export type AvailabilityUnit = {
  unit_id: number;
  unit_code: string;
  property_slug: string;
  blocked_periods: Array<{
    booking_code: string;
    check_in: string;
    check_out: string;
    status: string;
  }>;
};

export type AvailabilityResponse = {
  from: string;
  to: string;
  units: AvailabilityUnit[];
};

export type ReservationCreateResponse = {
  id: number;
  booking_code: string;
  status: string;
  check_in: string;
  check_out: string;
  property_slug: string;
};
