from __future__ import annotations

import logging
from typing import Any

import httpx

from apps.integrations.whatsapp.client import WhatsAppApiError
from apps.integrations.whatsapp.config import access_token_from_env, api_version_from_env

logger = logging.getLogger(__name__)


class WhatsAppMediaError(Exception):
    pass


def fetch_whatsapp_media(
    *,
    media_id: str,
    access_token: str | None = None,
    api_version: str | None = None,
) -> tuple[bytes, str]:
    """Download WhatsApp media binary via Meta Graph API."""
    token = (access_token or access_token_from_env()).strip()
    if not token:
        raise WhatsAppMediaError("WHATSAPP_ACCESS_TOKEN missing")
    if not media_id:
        raise WhatsAppMediaError("media_id missing")

    version = (api_version or api_version_from_env()).strip() or "v23.0"
    meta_url = f"https://graph.facebook.com/{version}/{media_id.strip()}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        meta_response = httpx.get(meta_url, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        raise WhatsAppMediaError(f"media metadata HTTP error: {exc}") from exc

    if meta_response.status_code >= 400:
        raise WhatsAppMediaError(
            f"media metadata error {meta_response.status_code}: {meta_response.text[:500]}"
        )

    meta = meta_response.json()
    if not isinstance(meta, dict):
        raise WhatsAppMediaError("media metadata is not JSON object")

    download_url = str(meta.get("url") or "").strip()
    mime_type = str(meta.get("mime_type") or "image/jpeg").strip()
    if not download_url:
        raise WhatsAppMediaError("media metadata missing url")

    try:
        file_response = httpx.get(
            download_url,
            headers=headers,
            timeout=60.0,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        raise WhatsAppMediaError(f"media download HTTP error: {exc}") from exc

    if file_response.status_code >= 400:
        raise WhatsAppMediaError(
            f"media download error {file_response.status_code}: {file_response.text[:200]}"
        )

    return file_response.content, mime_type


def extract_media_from_message(raw_message: dict[str, Any]) -> tuple[str, str, str]:
    """Return (media_id, mime_type, caption) from WhatsApp inbound message payload."""
    message_type = str(raw_message.get("type") or "").strip().lower()
    if message_type == "image":
        payload = raw_message.get("image") or {}
        return (
            str(payload.get("id") or "").strip(),
            str(payload.get("mime_type") or "image/jpeg").strip(),
            str(payload.get("caption") or "").strip(),
        )
    if message_type == "document":
        payload = raw_message.get("document") or {}
        return (
            str(payload.get("id") or "").strip(),
            str(payload.get("mime_type") or "application/octet-stream").strip(),
            str(payload.get("caption") or "").strip(),
        )
    return "", "", ""
