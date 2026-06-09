"""Deterministic corrections after LLM document OCR (side detection, image indices)."""

from __future__ import annotations

import re
from typing import Any

_BACK_OCR_MARKERS = frozenset(
    {
        "PESEL",
        "PERSONAL NUMBER",
        "ISSUING AUTHORITY",
        "ORGAN WYDAJ",
        "DATE OF ISSUE",
        "DATA WYDANIA",
        "PARENTS",
        "RODOWE",
        "RODZIC",
        "MIEJSCE URODZENIA",
        "PLACE OF BIRTH",
    }
)

_FRONT_OCR_MARKERS = frozenset(
    {
        "PODPIS",
        "SIGNATURE",
        "IMIONA/",
        "GIVEN NAMES",
        "NAZWISKO/",
        "SURNAME",
        "IDENTITY CARD",
        "DOWOD OSOBISTY",
    }
)


def _ocr_text_upper(item: dict) -> str:
    return str(item.get("ocr_text") or "").upper()


def _has_mrz_lines(item: dict) -> bool:
    lines = item.get("mrz_lines") or []
    if not isinstance(lines, list):
        return bool(str(lines or "").strip())
    return any(str(line).strip() for line in lines)


def infer_image_side(item: dict) -> str:
    """Return front|back|passport|unknown for a single images[] OCR row."""
    if not isinstance(item, dict):
        return "unknown"

    side = str(item.get("side") or "").strip().lower()
    if side in {"front", "back", "passport"}:
        inferred = side
    else:
        inferred = "unknown"

    text = _ocr_text_upper(item)
    has_mrz = _has_mrz_lines(item)

    back_score = sum(1 for marker in _BACK_OCR_MARKERS if marker in text)
    front_score = sum(1 for marker in _FRONT_OCR_MARKERS if marker in text)

    if has_mrz and back_score >= 1:
        return "back"
    if back_score >= 2 and back_score > front_score:
        return "back"
    if inferred == "front" and has_mrz and "PESEL" in text:
        return "back"
    if inferred == "unknown" and front_score >= 2:
        return "front"
    if inferred in {"front", "back", "passport"}:
        return inferred
    return "unknown"


def _image_meta_at(images: list, index: Any) -> dict | None:
    try:
        idx = int(index)
    except (TypeError, ValueError):
        return None
    if idx < 0 or idx >= len(images):
        return None
    item = images[idx]
    return item if isinstance(item, dict) else None


def _reconcile_person_image_indices(person: dict, images: list[dict]) -> None:
    """Align front_image_index / back_image_index with corrected images[].side."""
    front_idx = person.get("front_image_index")
    back_idx = person.get("back_image_index")

    front_meta = _image_meta_at(images, front_idx)
    back_meta = _image_meta_at(images, back_idx)

    if front_meta is not None and front_meta.get("side") == "back" and back_meta is None:
        person["back_image_index"] = front_idx
        person["front_image_index"] = None
        return

    if back_meta is not None and back_meta.get("side") == "front" and front_meta is None:
        person["front_image_index"] = back_idx
        person["back_image_index"] = None
        return

    if front_meta is not None and front_meta.get("side") == "back" and back_meta is not None:
        if back_meta.get("side") == "front":
            person["front_image_index"] = back_idx
            person["back_image_index"] = front_idx


def fixup_document_ocr_result(ocr_result: dict) -> dict:
    """Correct misclassified sides and person image indices before match/apply."""
    if not isinstance(ocr_result, dict):
        return ocr_result

    images_raw = ocr_result.get("images") or []
    images: list[dict] = [item for item in images_raw if isinstance(item, dict)]

    for item in images:
        item["side"] = infer_image_side(item)

    persons_raw = ocr_result.get("persons") or []
    persons: list[dict] = [item for item in persons_raw if isinstance(item, dict)]

    for person in persons:
        _reconcile_person_image_indices(person, images)

    ocr_result["images"] = images
    ocr_result["persons"] = persons
    return ocr_result


def normalize_document_number(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").upper())
