"""Pre-OCR hygiene: byte-hash dedup before LLM."""

from __future__ import annotations

import hashlib


def dedupe_image_bytes(
    image_bytes: list[bytes],
) -> tuple[list[bytes], list[int], list[int]]:
    """Return unique bytes, unique-slot→original index map, and dropped original indices."""
    unique_bytes: list[bytes] = []
    unique_to_original: list[int] = []
    dropped: list[int] = []
    seen: dict[str, int] = {}

    for orig_idx, data in enumerate(image_bytes):
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            dropped.append(orig_idx)
            continue
        seen[digest] = len(unique_bytes)
        unique_bytes.append(data)
        unique_to_original.append(orig_idx)

    return unique_bytes, unique_to_original, dropped


def remap_ocr_indices_to_original(
    ocr_result: dict,
    unique_to_original: list[int],
) -> dict:
    """Rewrite image/person indices from deduped OCR slots back to original sort orders."""
    if not unique_to_original:
        return ocr_result

    def _remap_idx(raw) -> int | None:
        if raw is None:
            return None
        try:
            ui = int(raw)
        except (TypeError, ValueError):
            return None
        if ui < 0 or ui >= len(unique_to_original):
            return None
        return unique_to_original[ui]

    images = ocr_result.get("images") or []
    if isinstance(images, list):
        for item in images:
            if not isinstance(item, dict):
                continue
            remapped = _remap_idx(item.get("index"))
            if remapped is not None:
                item["index"] = remapped

    persons = ocr_result.get("persons") or []
    if isinstance(persons, list):
        for person in persons:
            if not isinstance(person, dict):
                continue
            for key in ("front_image_index", "back_image_index"):
                remapped = _remap_idx(person.get(key))
                if remapped is not None:
                    person[key] = remapped

    return ocr_result
