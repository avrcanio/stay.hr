export const LEGAL_CONTACT = {
  legalName: "FINE STAR d.o.o.",
  controllerName: "FINE STAR d.o.o. (Stay.hr / Hospira)",
  brandNames: ["Stay.hr", "Hospira"] as const,
  websiteUrl: "https://stay.hr",
  email: "privacy@stay.hr",
  infoEmail: "info@stay.hr",
  address: "Bana Josipa Jelačića 58, 22000 Šibenik, Hrvatska",
  oib: "36619131370",
  lastUpdatedHr: "24. svibnja 2026.",
  lastUpdatedEn: "24 May 2026",
} as const;

export const PRIVACY_SECTIONS = [
  "whoWeAre",
  "dataWeCollect",
  "purposes",
  "accommodationRole",
  "recipients",
  "cookies",
  "retention",
  "rights",
  "complaint",
  "changes",
] as const;

export type PrivacySectionId = (typeof PRIVACY_SECTIONS)[number];

export const TERMS_SECTIONS = [
  "scope",
  "services",
  "guestBooking",
  "providers",
  "acceptableUse",
  "availability",
  "liability",
  "intellectualProperty",
  "termination",
  "law",
  "changes",
] as const;

export type TermsSectionId = (typeof TERMS_SECTIONS)[number];
