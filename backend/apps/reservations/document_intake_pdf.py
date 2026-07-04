"""Expand PDF uploads to JPEG pages before OpenAI Vision OCR."""

from __future__ import annotations

import logging

import fitz

logger = logging.getLogger(__name__)

PDF_MIME = "application/pdf"
JPEG_MIME = "image/jpeg"
MAX_PDF_PAGES = 10
PDF_RENDER_DPI = 200
_PDF_RENDER_MATRIX = fitz.Matrix(PDF_RENDER_DPI / 72, PDF_RENDER_DPI / 72)


def _pdf_pages_to_jpeg(pdf_bytes: bytes) -> list[bytes]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page_count = min(len(doc), MAX_PDF_PAGES)
        if len(doc) > MAX_PDF_PAGES:
            logger.warning(
                "PDF truncated for OCR: %s pages, limit %s",
                len(doc),
                MAX_PDF_PAGES,
            )
        pages: list[bytes] = []
        for page_idx in range(page_count):
            page = doc.load_page(page_idx)
            pix = page.get_pixmap(matrix=_PDF_RENDER_MATRIX)
            pages.append(pix.tobytes("jpeg"))
        return pages
    finally:
        doc.close()


def _is_pdf_mime(mime_type: str) -> bool:
    return mime_type.split(";")[0].strip().lower() == PDF_MIME


def expand_bytes_for_ocr(
    image_bytes: list[bytes],
    mime_types: list[str],
) -> tuple[list[bytes], list[str], list[int]]:
    """PDF pages → JPEG; images pass-through.

    Returns (ocr_bytes, ocr_mimes, ocr_to_source) where ocr_to_source[i] is the
    original source image index for OCR slot i.
    """
    if len(mime_types) != len(image_bytes):
        raise ValueError("mime_types length must match image_bytes length")

    ocr_bytes: list[bytes] = []
    ocr_mimes: list[str] = []
    ocr_to_source: list[int] = []

    for source_idx, (data, mime) in enumerate(zip(image_bytes, mime_types, strict=True)):
        if _is_pdf_mime(mime):
            for page_bytes in _pdf_pages_to_jpeg(data):
                ocr_bytes.append(page_bytes)
                ocr_mimes.append(JPEG_MIME)
                ocr_to_source.append(source_idx)
        else:
            ocr_bytes.append(data)
            ocr_mimes.append(mime)
            ocr_to_source.append(source_idx)

    return ocr_bytes, ocr_mimes, ocr_to_source


def remap_ocr_indices_to_source(ocr_result: dict, ocr_to_source: list[int]) -> dict:
    """Rewrite image/person indices from expanded OCR slots back to source image indices."""
    if not ocr_to_source:
        return ocr_result

    def _remap_idx(raw) -> int | None:
        if raw is None:
            return None
        try:
            ocr_idx = int(raw)
        except (TypeError, ValueError):
            return None
        if ocr_idx < 0 or ocr_idx >= len(ocr_to_source):
            return None
        return ocr_to_source[ocr_idx]

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


def source_indices_to_ocr_slots(
    source_indices: list[int],
    ocr_to_source: list[int],
) -> list[int]:
    """Map source image indices to expanded OCR slot indices."""
    wanted = set(source_indices)
    return [ocr_idx for ocr_idx, src in enumerate(ocr_to_source) if src in wanted]
