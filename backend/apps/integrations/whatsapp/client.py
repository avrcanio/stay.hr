from __future__ import annotations

import logging
from typing import Any

import httpx

from apps.integrations.whatsapp.config import (
    api_version_from_env,
    d360_api_base_url_from_env,
    d360_api_key_from_env,
    is_360dialog_provider,
)

logger = logging.getLogger(__name__)


class WhatsAppApiError(Exception):
    pass


def extract_outbound_wamid(response: dict[str, Any]) -> str:
    for item in response.get("messages") or []:
        wamid = str(item.get("id") or "").strip()
        if wamid:
            return wamid
    return ""


def send_text_message(
    *,
    phone_number_id: str,
    access_token: str,
    to_wa_id: str,
    body: str,
    api_version: str | None = None,
    provider: str | None = None,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": body},
    }

    if is_360dialog_provider(provider):
        base = (api_base_url or d360_api_base_url_from_env()).rstrip("/")
        url = f"{base}/messages"
        api_key = (access_token or d360_api_key_from_env()).strip()
        if not api_key:
            raise WhatsAppApiError("360dialog API key missing (D360_API_KEY)")
        headers = {
            "D360-API-KEY": api_key,
            "Content-Type": "application/json",
        }
    else:
        if not phone_number_id or not access_token:
            raise WhatsAppApiError("Meta WhatsApp credentials missing")
        version = (api_version or api_version_from_env()).strip() or "v23.0"
        url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        raise WhatsAppApiError(f"WhatsApp HTTP error: {exc}") from exc

    if response.status_code >= 400:
        logger.warning(
            "WhatsApp send failed",
            extra={"status_code": response.status_code, "body": response.text[:500]},
        )
        raise WhatsAppApiError(
            f"WhatsApp API error {response.status_code}: {response.text[:500]}"
        )

    data = response.json()
    if not isinstance(data, dict):
        raise WhatsAppApiError("WhatsApp API returned non-object JSON")
    return data
