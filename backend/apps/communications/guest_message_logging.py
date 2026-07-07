"""Structured logging and correlation IDs for guest message compose/send."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

GUEST_MESSAGE_COMPOSE_ATTEMPT = "guest_message.compose.attempt"
GUEST_MESSAGE_COMPOSE_SUCCESS = "guest_message.compose.success"
GUEST_MESSAGE_SEND_ATTEMPT = "guest_message.send.attempt"
GUEST_MESSAGE_SEND_SUCCESS = "guest_message.send.success"
GUEST_MESSAGE_SEND_ERROR = "guest_message.send.error"
GUEST_MESSAGE_WHATSAPP_API = "guest_message.whatsapp.api"
GUEST_MESSAGE_WHATSAPP_TEMPLATE = "guest_message.whatsapp.template"
GUEST_MESSAGE_WHATSAPP_HANDOFF = "guest_message.whatsapp.handoff"
GUEST_MESSAGE_WHATSAPP_BLOCKED = "guest_message.whatsapp.blocked"


def resolve_correlation_id(request) -> str:
    header = (request.headers.get("X-Correlation-Id") or "").strip()
    try:
        if header:
            parsed = uuid.UUID(header)
            return str(parsed)
    except ValueError:
        pass
    return str(uuid.uuid4())


def body_meta(body_text: str) -> dict:
    text = (body_text or "").strip()
    return {
        "body_length": len(text),
        "body_preview": text[:50] + ("…" if len(text) > 50 else ""),
    }


def guest_message_log_extra(
    *,
    event: str,
    request_id: str,
    reservation_id: int,
    tenant_slug: str,
    draft_id: int | None = None,
    channel: str = "",
    intent: str = "",
    **more: Any,
) -> dict:
    return {
        "event": event,
        "request_id": request_id,
        "reservation_id": reservation_id,
        "tenant_slug": tenant_slug,
        "draft_id": draft_id,
        "channel": channel,
        "intent": intent,
        **more,
    }


_GREP_KEYS = (
    "request_id",
    "reservation_id",
    "draft_id",
    "channel",
    "intent",
    "compose_ms",
    "send_ms",
    "meta_api_ms",
    "handoff_reason",
    "provider_error_code",
    "provider_error_subcode",
    "provider_message_id",
    "status",
    "template_name",
    "http_status",
)


def log_guest_message_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    parts = [event]
    for key in _GREP_KEYS:
        value = payload.get(key)
        if value is not None and value != "":
            parts.append(f"{key}={value}")
    logger.info(" ".join(parts), extra=payload)


class GuestMessageCorrelationMixin:
    """Resolve X-Correlation-Id on entry and echo on every response."""

    def dispatch(self, request, *args, **kwargs):
        request.guest_message_request_id = resolve_correlation_id(request)
        response = super().dispatch(request, *args, **kwargs)
        response["X-Correlation-Id"] = request.guest_message_request_id
        return response


class MetaApiTimer:
    """Context manager for meta_api_ms timing."""

    def __init__(self) -> None:
        self.started = 0.0
        self.elapsed_ms: int | None = None

    def __enter__(self) -> MetaApiTimer:
        self.started = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        self.elapsed_ms = int((time.perf_counter() - self.started) * 1000)
