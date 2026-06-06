from __future__ import annotations

import os

DEFAULT_D360_API_BASE_URL = "https://waba-v2.360dialog.io"


def webhook_verify_token_from_env() -> str:
    return os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "").strip()


def app_secret_from_env() -> str:
    return os.getenv("WHATSAPP_APP_SECRET", "").strip()


def api_version_from_env() -> str:
    return os.getenv("WHATSAPP_API_VERSION", "v23.0").strip() or "v23.0"


def provider_from_env() -> str:
    return os.getenv("WHATSAPP_PROVIDER", "meta").strip().lower()


def d360_api_key_from_env() -> str:
    return os.getenv("D360_API_KEY", "").strip()


def d360_api_base_url_from_env() -> str:
    value = os.getenv("D360_API_BASE_URL", DEFAULT_D360_API_BASE_URL).strip()
    return value.rstrip("/") if value else DEFAULT_D360_API_BASE_URL


def webhook_verify_signature_from_env() -> bool:
    raw = os.getenv("WHATSAPP_WEBHOOK_VERIFY_SIGNATURE", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    # 360dialog often delivers webhooks without Meta X-Hub-Signature-256.
    return provider_from_env() != "360dialog"


def is_360dialog_provider(provider: str | None = None) -> bool:
    value = (provider or provider_from_env()).strip().lower()
    return value in ("360dialog", "d360")
