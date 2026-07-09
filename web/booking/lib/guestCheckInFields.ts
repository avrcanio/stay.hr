export type FormSex = "" | "female" | "male";
export type FormDocumentType = "" | "identity_card" | "passport";

/** Map stored guest / OCR sex codes to wizard select values. */
export function normalizeSexForForm(value: string | null | undefined): FormSex {
  const raw = (value || "").trim().toLowerCase();
  if (!raw) return "";
  if (
    raw === "female" ||
    raw === "f" ||
    raw === "ž" ||
    raw === "z" ||
    raw.includes("žen") ||
    raw.includes("zen")
  ) {
    return "female";
  }
  if (raw === "male" || raw === "m" || raw.includes("muš") || raw.includes("mus")) {
    return "male";
  }
  return "";
}

/** Map stored guest / OCR document labels to wizard select values. */
export function normalizeDocumentTypeForForm(
  value: string | null | undefined,
): FormDocumentType {
  const raw = (value || "").trim().toLowerCase();
  if (!raw) return "";
  if (raw === "passport" || raw === "putovnica" || raw.includes("passport")) {
    return "passport";
  }
  if (
    raw === "identity_card" ||
    raw === "national_id" ||
    raw === "osobna iskaznica" ||
    raw.includes("osobna") ||
    raw.includes("identity") ||
    raw === "id"
  ) {
    return "identity_card";
  }
  return "";
}
