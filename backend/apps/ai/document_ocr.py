"""OpenAI Vision OCR for shared document photos."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o"
DEFAULT_TIMEOUT_SEC = 90.0

SYSTEM_PROMPT = """You are an ID document OCR assistant for hotel reception check-in.
Analyze all provided document photos. They may arrive in random order from WhatsApp.

Rules:
- Return one `images[]` row for **every** input index (0..N-1).
- Use side "non_document" for contracts, letters, membership cards (e.g. ADAC), or photos
  without MRZ or portrait — not identity documents.
- Ignore `non_document` images when building `persons[]`.
- Emit **one person per unique document number**; scan **all** indices before finishing.
- Do NOT assume photo order. Pair front/back of the same person by MRZ surname/given names on the back.
- Extract MRZ lines when visible (passport biodata or ID card back lower third).
- For EU national ID cards: front has portrait and name; back has MRZ.
- German Personalausweis: field [a] Name/Surname is the current surname (surnames).
  Field [b] Geburtsname/Name at birth is NOT the surname — never put birth name in surnames.
  Prefer MRZ surname (line before << or first <) when visible on the back.
- For passports: biodata page is both front and passport side.
- face_bbox: normalized 0-1 coordinates (x, y, w, h) of the portrait photo on the front/biodata page.
  Measure from the actual image. Use null if no portrait is visible. Do NOT copy example values.
- Dates as ISO YYYY-MM-DD when possible.
- nationality and issuing country as ISO 3166-1 alpha-3 when possible (DEU, POL, HRV, AUT, ...).
- sex: M or F when known. For EU ID cards read the Sex/Geschlecht/S field on the front — required for eVisitor.

Return ONLY valid JSON with this shape:
{
  "images": [{"index": 0, "side": "front|back|passport|non_document|unknown", "mrz_lines": ["..."], "ocr_text": "..."}],
  "persons": [{
    "given_names": "",
    "surnames": "",
    "document_number": "",
    "nationality": "",
    "date_of_birth": "",
    "date_of_expiry": "",
    "sex": "",
    "address": "",
    "document_type": "passport|national_id",
    "front_image_index": 0,
    "back_image_index": null,
    "mrz_lines": [],
    "face_bbox": null
  }]
}
"""

ORPHAN_SYSTEM_PROMPT = """You are an ID document OCR assistant. Extract identity documents ONLY.
The photos may include non-ID images — ignore those.

Return ONLY valid JSON:
{
  "images": [{"index": 0, "side": "front|back|passport|non_document|unknown", "mrz_lines": [], "ocr_text": ""}],
  "persons": [{
    "given_names": "",
    "surnames": "",
    "document_number": "",
    "nationality": "",
    "date_of_birth": "",
    "date_of_expiry": "",
    "sex": "",
    "address": "",
    "document_type": "passport|national_id",
    "front_image_index": 0,
    "back_image_index": null,
    "mrz_lines": [],
    "face_bbox": null
  }]
}
If no identity documents found, return {"images": [...], "persons": []}.
"""


class DocumentOcrError(Exception):
    """Vision OCR failed."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def ocr_configured() -> bool:
    provider = _env("DOCUMENT_OCR_LLM_PROVIDER", "openai").lower()
    api_key = _ocr_api_key()
    return provider == "openai" and bool(api_key)


def _ocr_api_key() -> str:
    key = _env("DOCUMENT_OCR_LLM_API_KEY")
    if key:
        return key
    return _env("GUEST_COMPOSE_LLM_API_KEY")


def ocr_model() -> str:
    return _env("DOCUMENT_OCR_LLM_MODEL", DEFAULT_MODEL)


def ocr_timeout() -> float:
    raw = _env("DOCUMENT_OCR_LLM_TIMEOUT_SEC")
    if not raw:
        return DEFAULT_TIMEOUT_SEC
    try:
        return max(10.0, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SEC


def _encode_image_bytes(data: bytes, mime: str = "image/jpeg") -> str:
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _openai_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        err = payload.get("error") or {}
        message = (err.get("message") or "").strip()
        code = (err.get("code") or "").strip()
    except (json.JSONDecodeError, AttributeError, TypeError):
        message = ""
        code = ""
    if code == "missing_scope":
        return (
            "OCR API key nema dozvolu za vision (missing scope model.request). "
            "Na platform.openai.com/api-keys kreiraj ključ s punim pristupom "
            "ili uključenim Chat Completions / model.request."
        )
    if message:
        return f"OCR API error: {message}"
    if response.status_code == 401:
        return "OCR API unauthorized (check API key)"
    return f"OCR API error ({response.status_code})"


def complete_vision_json(
    *,
    user_text: str,
    image_bytes_list: list[bytes],
    mime_types: list[str] | None = None,
    model: str | None = None,
    timeout: float | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Call OpenAI chat/completions with vision images; return parsed JSON dict."""
    provider = _env("DOCUMENT_OCR_LLM_PROVIDER", "openai").lower()
    if provider != "openai":
        raise DocumentOcrError(f"Unsupported OCR provider: {provider}")

    api_key = _ocr_api_key()
    if not api_key:
        raise DocumentOcrError("DOCUMENT_OCR_LLM_API_KEY is not configured")

    if not image_bytes_list:
        raise DocumentOcrError("No images provided")

    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    mimes = mime_types or ["image/jpeg"] * len(image_bytes_list)
    for idx, (raw, mime) in enumerate(zip(image_bytes_list, mimes, strict=True)):
        content.append(
            {
                "type": "text",
                "text": f"Image index {idx}:",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _encode_image_bytes(raw, mime), "detail": "high"},
            }
        )

    payload = {
        "model": model or ocr_model(),
        "messages": [
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout_sec = timeout if timeout is not None else ocr_timeout()

    try:
        response = httpx.post(
            OPENAI_CHAT_URL,
            json=payload,
            headers=headers,
            timeout=timeout_sec,
        )
    except httpx.TimeoutException as exc:
        raise DocumentOcrError("OCR request timed out") from exc
    except httpx.HTTPError as exc:
        raise DocumentOcrError(f"OCR HTTP error: {exc}") from exc

    if response.status_code == 429:
        raise DocumentOcrError("OCR rate limit exceeded")
    if response.status_code >= 400:
        logger.warning(
            "OCR API error",
            extra={"status": response.status_code, "body": response.text[:500]},
        )
        raise DocumentOcrError(_openai_error_message(response))

    data = response.json()
    try:
        raw_content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DocumentOcrError("Unexpected OCR response shape") from exc

    text = (raw_content or "").strip()
    if not text:
        raise DocumentOcrError("OCR returned empty response")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DocumentOcrError("OCR returned invalid JSON") from exc

    if not isinstance(parsed, dict):
        raise DocumentOcrError("OCR JSON root must be an object")
    return parsed


def run_document_batch_ocr(*, image_bytes_list: list[bytes], mime_types: list[str] | None = None) -> dict[str, Any]:
    """OCR a batch of document photos; returns structured persons/images."""
    count = len(image_bytes_list)
    user_text = (
        f"Analyze these {count} document photo(s) from WhatsApp. "
        "Identify each person, pair front/back correctly using MRZ names, "
        "mark non-ID images as non_document, and extract all check-in fields."
    )
    return complete_vision_json(
        user_text=user_text,
        image_bytes_list=image_bytes_list,
        mime_types=mime_types,
    )


ORPHAN_CHUNK_SIZE = 6


def run_orphan_document_ocr(
    *,
    image_bytes_list: list[bytes],
    mime_types: list[str] | None = None,
    orphan_indices: list[int],
) -> dict[str, Any]:
    """Second-pass OCR on unassigned image indices only."""
    if not orphan_indices:
        return {"images": [], "persons": []}

    merged_images: list[dict] = []
    merged_persons: list[dict] = []

    for chunk_start in range(0, len(orphan_indices), ORPHAN_CHUNK_SIZE):
        chunk_indices = orphan_indices[chunk_start : chunk_start + ORPHAN_CHUNK_SIZE]
        chunk_bytes = [image_bytes_list[i] for i in chunk_indices]
        chunk_mimes = None
        if mime_types:
            chunk_mimes = [mime_types[i] for i in chunk_indices]

        user_text = (
            f"These {len(chunk_indices)} photo(s) were not matched to any guest yet. "
            f"Original indices: {chunk_indices}. "
            "Extract identity documents only; pair front/back by MRZ names."
        )
        result = complete_vision_json(
            user_text=user_text,
            image_bytes_list=chunk_bytes,
            mime_types=chunk_mimes,
            system_prompt=ORPHAN_SYSTEM_PROMPT,
        )

        index_map = {local_idx: orig_idx for local_idx, orig_idx in enumerate(chunk_indices)}

        for item in result.get("images") or []:
            if not isinstance(item, dict):
                continue
            local = int(item.get("index", -1))
            if local in index_map:
                item["index"] = index_map[local]
                merged_images.append(item)

        for person in result.get("persons") or []:
            if not isinstance(person, dict):
                continue
            for key in ("front_image_index", "back_image_index"):
                raw = person.get(key)
                if raw is None:
                    continue
                try:
                    local = int(raw)
                except (TypeError, ValueError):
                    continue
                if local in index_map:
                    person[key] = index_map[local]
            merged_persons.append(person)

    return {"images": merged_images, "persons": merged_persons}


def merge_persons(existing: list[dict], extra: list[dict]) -> list[dict]:
    """Merge orphan-pass persons; dedupe by document number and MRZ surname."""
    from apps.reservations.document_intake_ocr_fixup import normalize_document_number

    merged = [dict(p) for p in existing if isinstance(p, dict)]
    seen_docs: set[str] = set()
    seen_surnames: set[str] = set()

    for person in merged:
        doc = normalize_document_number(str(person.get("document_number") or ""))
        if doc:
            seen_docs.add(doc)
        surname = str(person.get("surnames") or "").strip().upper()
        if surname:
            seen_surnames.add(surname)

    for person in extra:
        if not isinstance(person, dict):
            continue
        doc = normalize_document_number(str(person.get("document_number") or ""))
        surname = str(person.get("surnames") or "").strip().upper()
        if doc and doc in seen_docs:
            continue
        if not doc and surname and surname in seen_surnames:
            continue
        merged.append(dict(person))
        if doc:
            seen_docs.add(doc)
        if surname:
            seen_surnames.add(surname)

    return merged
