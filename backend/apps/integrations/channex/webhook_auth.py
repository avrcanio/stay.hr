from __future__ import annotations

import os
import secrets
from typing import Any

from django.http import HttpRequest

WEBHOOK_HEADER_NAME = "X-Stay-Channex-Webhook"
WEBHOOK_QUERY_PROVIDER = "provider"
WEBHOOK_QUERY_ENV = "env"
EXPECTED_PROVIDER = "stay"
EXPECTED_ENV = "staging"


def generate_webhook_secret() -> str:
    return secrets.token_urlsafe(32)


def webhook_secret_from_env() -> str:
    return os.getenv("CHANNEX_WEBHOOK_SECRET", "").strip()


def verify_channex_webhook_request(request: HttpRequest, *, config_secret: str) -> bool:
    secret = (config_secret or webhook_secret_from_env()).strip()
    if not secret:
        return False

    header_value = (request.headers.get(WEBHOOK_HEADER_NAME) or "").strip()
    if not header_value or not secrets.compare_digest(header_value, secret):
        return False

    if request.GET.get(WEBHOOK_QUERY_PROVIDER) != EXPECTED_PROVIDER:
        return False

    env = request.GET.get(WEBHOOK_QUERY_ENV, EXPECTED_ENV)
    if env and env != EXPECTED_ENV:
        return False

    return True


def extract_event_name(body: dict[str, Any]) -> str:
    return str(body.get("event") or "")
