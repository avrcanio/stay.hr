from __future__ import annotations

import logging
from typing import Any

import httpx

from apps.integrations.whatsapp.config import access_token_from_env, api_version_from_env

logger = logging.getLogger(__name__)


class WhatsAppApiError(Exception):
    pass


def extract_outbound_wamid(response: dict[str, Any]) -> str:
    for item in response.get("messages") or []:
        wamid = str(item.get("id") or "").strip()
        if wamid:
            return wamid
    return ""


def _resolve_access_token(access_token: str | None) -> str:
    token = (access_token or access_token_from_env()).strip()
    if not token:
        raise WhatsAppApiError("Meta WhatsApp access token missing (WHATSAPP_ACCESS_TOKEN)")
    return token


def _post_whatsapp_message(
    *,
    payload: dict[str, Any],
    phone_number_id: str,
    access_token: str | None = None,
    api_version: str | None = None,
) -> dict[str, Any]:
    if not phone_number_id:
        raise WhatsAppApiError("Meta WhatsApp phone_number_id missing")
    token = _resolve_access_token(access_token)
    version = (api_version or api_version_from_env()).strip() or "v23.0"
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
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


def send_text_message(
    *,
    phone_number_id: str,
    to_wa_id: str,
    body: str,
    access_token: str | None = None,
    api_version: str | None = None,
) -> dict[str, Any]:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": body},
    }

    return _post_whatsapp_message(
        payload=payload,
        phone_number_id=phone_number_id,
        access_token=access_token,
        api_version=api_version,
    )


def send_template_message(
    *,
    phone_number_id: str,
    to_wa_id: str,
    template_name: str,
    language_code: str,
    body_parameters: list[str],
    header_image_url: str | None = None,
    access_token: str | None = None,
    api_version: str | None = None,
) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    if header_image_url:
        components.append(
            {
                "type": "header",
                "parameters": [
                    {
                        "type": "image",
                        "image": {"link": header_image_url},
                    }
                ],
            }
        )
    components.append(
        {
            "type": "body",
            "parameters": [{"type": "text", "text": value} for value in body_parameters],
        }
    )

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components,
        },
    }

    return _post_whatsapp_message(
        payload=payload,
        phone_number_id=phone_number_id,
        access_token=access_token,
        api_version=api_version,
    )


def send_interactive_button_message(
    *,
    phone_number_id: str,
    to_wa_id: str,
    body: str,
    buttons: list[tuple[str, str]],
    access_token: str | None = None,
    api_version: str | None = None,
) -> dict[str, Any]:
    """Send WhatsApp interactive reply buttons (max 3). buttons: list of (id, title)."""
    action_buttons = [
        {
            "type": "reply",
            "reply": {"id": btn_id, "title": (title or btn_id)[:20]},
        }
        for btn_id, title in buttons[:3]
    ]
    if not action_buttons:
        raise WhatsAppApiError("interactive message requires at least one button")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": (body or "")[:1024]},
            "action": {"buttons": action_buttons},
        },
    }

    return _post_whatsapp_message(
        payload=payload,
        phone_number_id=phone_number_id,
        access_token=access_token,
        api_version=api_version,
    )


def upload_media(
    *,
    file_bytes: bytes,
    mime_type: str,
    filename: str,
    phone_number_id: str,
    access_token: str | None = None,
    api_version: str | None = None,
) -> str:
    """Upload media to WhatsApp; returns media_id."""
    if not file_bytes:
        raise WhatsAppApiError("empty media file")
    if not phone_number_id:
        raise WhatsAppApiError("Meta WhatsApp phone_number_id missing")

    token = _resolve_access_token(access_token)
    version = (api_version or api_version_from_env()).strip() or "v23.0"
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": (filename or "image.jpg", file_bytes, mime_type or "image/jpeg")}
    data = {"messaging_product": "whatsapp", "type": mime_type or "image/jpeg"}

    try:
        response = httpx.post(url, data=data, files=files, headers=headers, timeout=60.0)
    except httpx.HTTPError as exc:
        raise WhatsAppApiError(f"WhatsApp media upload HTTP error: {exc}") from exc

    if response.status_code >= 400:
        logger.warning(
            "WhatsApp media upload failed",
            extra={"status_code": response.status_code, "body": response.text[:500]},
        )
        raise WhatsAppApiError(
            f"WhatsApp media upload error {response.status_code}: {response.text[:500]}"
        )

    payload = response.json()
    if not isinstance(payload, dict):
        raise WhatsAppApiError("WhatsApp media upload returned non-object JSON")
    media_id = str(payload.get("id") or "").strip()
    if not media_id:
        raise WhatsAppApiError("WhatsApp media upload missing id")
    return media_id


def send_image_message(
    *,
    phone_number_id: str,
    to_wa_id: str,
    media_id: str,
    caption: str = "",
    access_token: str | None = None,
    api_version: str | None = None,
) -> dict[str, Any]:
    image_payload: dict[str, Any] = {"id": media_id}
    caption_text = (caption or "").strip()
    if caption_text:
        image_payload["caption"] = caption_text

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "image",
        "image": image_payload,
    }

    return _post_whatsapp_message(
        payload=payload,
        phone_number_id=phone_number_id,
        access_token=access_token,
        api_version=api_version,
    )
