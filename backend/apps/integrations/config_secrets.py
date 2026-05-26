from __future__ import annotations

from typing import Any

from apps.integrations.models import IntegrationConfig

PROVIDER_SECRET_KEYS: dict[str, list[str]] = {
    IntegrationConfig.Provider.CHANNEX: ["api_key", "webhook_secret"],
    IntegrationConfig.Provider.WHATSAPP: ["access_token"],
    IntegrationConfig.Provider.EVISITOR: ["password", "api_key"],
}

SECRET_LABELS: dict[str, str] = {
    "api_key": "API key",
    "webhook_secret": "Webhook secret",
    "access_token": "Access token",
    "password": "Password",
}


def credentials_status(provider: str, config: dict[str, Any]) -> dict[str, bool]:
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
        label = SECRET_LABELS.get(key, key)
        parts.append(f"{label}: {'set' if is_set else 'not set'}")
    return "; ".join(parts)
