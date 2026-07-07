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


def build_dropped_to_canonical_map(
    image_bytes: list[bytes],
    dropped_indices: list[int],
) -> dict[int, int]:
    """Map each dropped original index to the first-seen (canonical) original index."""
    seen: dict[str, int] = {}
    dropped_map: dict[int, int] = {}
    dropped_set = set(dropped_indices)

    for orig_idx, data in enumerate(image_bytes):
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            if orig_idx in dropped_set:
                dropped_map[orig_idx] = seen[digest]
            continue
        seen[digest] = orig_idx

    return dropped_map


def canonicalize_person_image_indices(
    persons: list[dict],
    dropped_to_canonical: dict[int, int],
) -> list[dict]:
    """Rewrite person front/back indices that point at dropped duplicates."""
    if not dropped_to_canonical:
        return persons

    def _canonicalize(raw) -> int | None:
        if raw is None:
            return None
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            return None
        return dropped_to_canonical.get(idx, idx)

    updated: list[dict] = []
    for person in persons:
        if not isinstance(person, dict):
            updated.append(person)
            continue
        copy = dict(person)
        for key in ("front_image_index", "back_image_index"):
            if key in copy:
                canonical = _canonicalize(copy.get(key))
                if canonical is not None:
                    copy[key] = canonical
        updated.append(copy)
    return updated


def validate_no_dropped_references(
    ocr_result: dict,
    dropped_indices: list[int],
) -> None:
    """Raise ValueError if persons[] still reference dropped image indices."""
    if not dropped_indices:
        return
    dropped_set = set(dropped_indices)
    persons = ocr_result.get("persons") or []
    if not isinstance(persons, list):
        return

    for person_index, person in enumerate(persons):
        if not isinstance(person, dict):
            continue
        for key in ("front_image_index", "back_image_index"):
            raw = person.get(key)
            if raw is None:
                continue
            try:
                idx = int(raw)
            except (TypeError, ValueError):
                continue
            if idx in dropped_set:
                raise ValueError(
                    f"persons[{person_index}].{key} references dropped image index {idx}"
                )
