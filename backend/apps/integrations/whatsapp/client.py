from __future__ import annotations

import logging
from typing import Any

import httpx

from apps.integrations.whatsapp.config import api_version_from_env

logger = logging.getLogger(__name__)


class WhatsAppApiError(Exception):
    pass


def send_text_message(
    *,
    phone_number_id: str,
    access_token: str,
    to_wa_id: str,
    body: str,
    api_version: str | None = None,
) -> dict[str, Any]:
    version = (api_version or api_version_from_env()).strip() or "v23.0"
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": body},
    }
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
