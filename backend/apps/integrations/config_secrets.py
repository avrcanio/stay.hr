from __future__ import annotations

from typing import Any

from apps.integrations.models import IntegrationConfig
from apps.integrations.whatsapp.config import access_token_from_env

PROVIDER_SECRET_KEYS: dict[str, list[str]] = {
    IntegrationConfig.Provider.CHANNEX: ["api_key", "webhook_secret"],
    IntegrationConfig.Provider.WHATSAPP: [],
    IntegrationConfig.Provider.EVISITOR: ["password", "api_key"],
}

SECRET_LABELS: dict[str, str] = {
    "api_key": "API key",
    "webhook_secret": "Webhook secret",
    "access_token": "Access token",
    "password": "Password",
}


def credentials_status(provider: str, config: dict[str, Any]) -> dict[str, bool]:
    if provider == IntegrationConfig.Provider.WHATSAPP:
        return {
            "phone_number_id": bool(str(config.get("phone_number_id") or "").strip()),
            "access_token_env": bool(access_token_from_env()),
        }
    keys = PROVIDER_SECRET_KEYS.get(provider, [])
    return {key: bool(str(config.get(key) or "").strip()) for key in keys}


def credentials_complete(provider: str, config: dict[str, Any]) -> bool:
    status = credentials_status(provider, config)
    if not status:
        return True
    return all(status.values())


def credentials_status_summary(provider: str, config: dict[str, Any]) -> str:
    status = credentials_status(provider, config)
    if not status:
        return "—"
    parts = []
    for key, is_set in status.items():
        if key == "access_token_env":
            label = "WHATSAPP_ACCESS_TOKEN (.env)"
        elif key == "phone_number_id":
            label = "Phone number ID"
        else:
            label = SECRET_LABELS.get(key, key)
        parts.append(f"{label}: {'set' if is_set else 'not set'}")
    return "; ".join(parts)
