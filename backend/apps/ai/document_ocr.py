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
- Do NOT assume photo order. Pair front/back of the same person by MRZ surname/given names on the back.
- Extract MRZ lines when visible (passport biodata or ID card back lower third).
- For EU national ID cards: front has portrait and name; back has MRZ.
- For passports: biodata page is both front and passport side.
- face_bbox: normalized 0-1 coordinates (x, y, w, h) of the portrait photo on the front/biodata page.
  Measure from the actual image. Use null if no portrait is visible. Do NOT copy example values.
- Dates as ISO YYYY-MM-DD when possible.
- nationality and issuing country as ISO 3166-1 alpha-3 when possible (DEU, POL, HRV, AUT, ...).
- sex: M or F when known. For EU ID cards read the Sex/Geschlecht/S field on the front — required for eVisitor.

Return ONLY valid JSON with this shape:
{
  "images": [{"index": 0, "side": "front|back|passport|unknown", "mrz_lines": ["..."], "ocr_text": "..."}],
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
            {"role": "system", "content": SYSTEM_PROMPT},
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
        "and extract all check-in fields."
    )
    return complete_vision_json(
        user_text=user_text,
        image_bytes_list=image_bytes_list,
        mime_types=mime_types,
    )
