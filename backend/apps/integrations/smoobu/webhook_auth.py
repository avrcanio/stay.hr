from __future__ import annotations

import os
import secrets

from django.http import HttpRequest

WEBHOOK_HEADER_NAME = "X-Stay-Smoobu-Webhook"
WEBHOOK_QUERY_SECRET = "secret"


def webhook_secret_from_env() -> str:
    return os.getenv("SMOOBU_WEBHOOK_SECRET", "").strip()


def resolve_webhook_secret(config_secret: str) -> str:
    return (config_secret or webhook_secret_from_env()).strip()


def verify_smoobu_webhook_request(request: HttpRequest, *, config_secret: str) -> bool:
    secret = resolve_webhook_secret(config_secret)
    if not secret:
        return False

    header_value = (request.headers.get(WEBHOOK_HEADER_NAME) or "").strip()
    query_value = (request.GET.get(WEBHOOK_QUERY_SECRET) or "").strip()
    provided = header_value or query_value
    if not provided:
        return False
    return secrets.compare_digest(provided, secret)
