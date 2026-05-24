from __future__ import annotations

import hashlib
import hmac
import secrets

from django.http import HttpRequest

from apps.integrations.whatsapp.config import app_secret_from_env, webhook_verify_token_from_env

SIGNATURE_HEADER = "X-Hub-Signature-256"


def _constant_time_token_match(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    return secrets.compare_digest(
        provided.encode("utf-8"),
        expected.encode("utf-8"),
    )


def verify_webhook_subscription(request: HttpRequest) -> str | None:
    """Return hub.challenge when Meta verify handshake succeeds."""
    mode = (request.GET.get("hub.mode") or "").strip()
    token = (request.GET.get("hub.verify_token") or "").strip()
    challenge = (request.GET.get("hub.challenge") or "").strip()
    expected = webhook_verify_token_from_env()
    if not expected:
        return None
    if mode == "subscribe" and _constant_time_token_match(token, expected):
        return challenge
    return None


def verify_webhook_signature(request: HttpRequest, *, raw_body: bytes) -> bool:
    app_secret = app_secret_from_env()
    if not app_secret:
        return False

    signature = (request.headers.get(SIGNATURE_HEADER) or "").strip()
    if not signature.startswith("sha256="):
        return False

    expected = signature.removeprefix("sha256=")
    computed = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return secrets.compare_digest(computed, expected)
