from __future__ import annotations

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
