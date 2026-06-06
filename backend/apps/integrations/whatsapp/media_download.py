from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from apps.integrations.whatsapp.client import WhatsAppApiError
from apps.integrations.whatsapp.config import d360_api_base_url_from_env, d360_api_key_from_env

logger = logging.getLogger(__name__)


class WhatsAppMediaError(Exception):
    pass


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"D360-API-KEY": api_key}


def rewrite_d360_media_download_url(download_url: str, *, api_base_url: str) -> str:
    """Rewrite Meta CDN media URL to 360dialog API host (required for authenticated download)."""
    cleaned = download_url.replace("\\/", "/").replace("\\", "")
    parsed = urlparse(cleaned)
    base = api_base_url.rstrip("/")
    parsed_base = urlparse(base if "://" in base else f"https://{base}")
    return urlunparse(
        (
            parsed_base.scheme or "https",
            parsed_base.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def fetch_whatsapp_media(*, media_id: str, api_key: str | None = None, api_base_url: str | None = None) -> tuple[bytes, str]:
    """Download WhatsApp media binary via 360dialog Cloud API."""
    key = (api_key or d360_api_key_from_env()).strip()
    if not key:
        raise WhatsAppMediaError("D360_API_KEY missing")
    if not media_id:
        raise WhatsAppMediaError("media_id missing")

    base = (api_base_url or d360_api_base_url_from_env()).rstrip("/")
    meta_url = f"{base}/{media_id.strip()}"
    headers = _auth_headers(key)

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

    download_url = rewrite_d360_media_download_url(download_url, api_base_url=base)

    try:
        file_response = httpx.get(download_url, headers=headers, timeout=60.0, follow_redirects=True)
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
