"""Stable failure-reason API for document intake OCR telemetry."""

from __future__ import annotations

from enum import StrEnum


class OCRFailureReason(StrEnum):
    """Public failure-reason codes (lowercase snake_case JSON values)."""

    NO_MRZ = "no_mrz"
    MRZ_PARTIAL = "mrz_partial"
    FRONT_NOT_FOUND = "front_not_found"
    BACK_NOT_FOUND = "back_not_found"
    IMAGE_TOO_SMALL = "image_too_small"
    FACE_ONLY = "face_only"
    OCR_UNDER_EXTRACTED = "ocr_under_extracted"
    UNASSIGNED_IMAGES = "unassigned_images"
    UNKNOWN_PERSON = "unknown_person"
    NON_DOCUMENT_IMAGE = "non_document"
    OCR_FAILED = "ocr_failed"
    # --- reserved (not deprecated): enum exists for stable API / future PRs; OCR-D does not emit ---
    IMAGE_BLURRY = "image_blurry"  # reserved → OCR-E
    IMAGE_OVEREXPOSED = "image_overexposed"  # reserved → OCR-E
    GLARE = "glare"  # reserved → OCR-E
    CROP_FAILURE = "crop_failure"  # reserved
    LOW_CONFIDENCE = "low_confidence"  # reserved → OCR-F (LLM confidence)
    GPT_UNCERTAIN = "gpt_uncertain"  # reserved → OCR-F


_REASON_LABELS_HR: dict[OCRFailureReason, str] = {
    OCRFailureReason.NO_MRZ: "MRZ nije prepoznat",
    OCRFailureReason.MRZ_PARTIAL: "MRZ djelomično prepoznat",
    OCRFailureReason.FRONT_NOT_FOUND: "Prednja strana nije pronađena",
    OCRFailureReason.BACK_NOT_FOUND: "Stražnja strana nije pronađena",
    OCRFailureReason.IMAGE_TOO_SMALL: "Slika premala",
    OCRFailureReason.FACE_ONLY: "Samo portret bez podataka",
    OCRFailureReason.OCR_UNDER_EXTRACTED: "OCR nije izvukao sve goste",
    OCRFailureReason.UNASSIGNED_IMAGES: "Nepovezane slike",
    OCRFailureReason.UNKNOWN_PERSON: "Nepoznata osoba",
    OCRFailureReason.NON_DOCUMENT_IMAGE: "Nije dokument",
    OCRFailureReason.OCR_FAILED: "OCR nije uspio",
    OCRFailureReason.IMAGE_BLURRY: "Slika mutna",
    OCRFailureReason.IMAGE_OVEREXPOSED: "Slika previše osvijetljena",
    OCRFailureReason.GLARE: "Odsjaj na slici",
    OCRFailureReason.CROP_FAILURE: "Neuspješno rezanje",
    OCRFailureReason.LOW_CONFIDENCE: "Niska pouzdanost",
    OCRFailureReason.GPT_UNCERTAIN: "LLM nesiguran",
}


def reason_label(reason: OCRFailureReason | str, *, lang: str = "hr") -> str:
    """Human-readable label for operator UI (future OCR-G)."""
    if isinstance(reason, str):
        try:
            reason = OCRFailureReason(reason)
        except ValueError:
            return reason
    if lang == "hr":
        return _REASON_LABELS_HR.get(reason, reason.value)
    return reason.value
