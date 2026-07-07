from __future__ import annotations

import json
import re

import httpx

from apps.integrations.whatsapp.client import WhatsAppApiError

_TRANSIENT_HTTP_CODES = frozenset({502, 503, 504})


def is_transient_whatsapp_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPError) and not isinstance(exc, httpx.HTTPStatusError):
        return True
    if not isinstance(exc, WhatsAppApiError):
        return False
    msg = str(exc)
    for code in _TRANSIENT_HTTP_CODES:
        if f" {code}:" in msg or f"error {code}" in msg.lower():
            return True
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return True
    return False


def is_whatsapp_session_api_error(exc: WhatsAppApiError) -> bool:
    msg = str(exc).lower()
    markers = (
        "131047",
        "re-engagement",
        "reengagement",
        "24 hour",
        "24-hour",
        "outside",
        "session",
        "window",
    )
    return any(marker in msg for marker in markers)


def parse_meta_api_error(exc: WhatsAppApiError) -> dict:
    """Parse Meta Graph API error fields from WhatsAppApiError message."""
    msg = str(exc)
    result: dict = {
        "provider_status": None,
        "provider_error_code": None,
        "provider_error_subcode": None,
    }
    status_match = re.search(r"WhatsApp API error (\d+):", msg, re.I)
    if status_match:
        result["provider_status"] = int(status_match.group(1))
    json_start = msg.find("{")
    if json_start >= 0:
        try:
            body = json.loads(msg[json_start:])
            error = body.get("error") or {}
            if error.get("code") is not None:
                result["provider_error_code"] = error.get("code")
            if error.get("error_subcode") is not None:
                result["provider_error_subcode"] = error.get("error_subcode")
        except json.JSONDecodeError:
            pass
    if result["provider_error_code"] is None:
        code_match = re.search(r"\b(131\d{3}|132\d{3})\b", msg)
        if code_match:
            result["provider_error_code"] = int(code_match.group(1))
    return result
