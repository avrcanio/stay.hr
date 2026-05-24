from __future__ import annotations

import os


def webhook_verify_token_from_env() -> str:
    return os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "").strip()


def app_secret_from_env() -> str:
    return os.getenv("WHATSAPP_APP_SECRET", "").strip()


def api_version_from_env() -> str:
    return os.getenv("WHATSAPP_API_VERSION", "v23.0").strip() or "v23.0"
