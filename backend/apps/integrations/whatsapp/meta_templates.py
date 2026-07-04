from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from apps.integrations.whatsapp.client import WhatsAppApiError
from apps.integrations.whatsapp.config import api_version_from_env

logger = logging.getLogger(__name__)


class MetaTemplateApiError(WhatsAppApiError):
    pass


def _graph_base_url() -> str:
    version = api_version_from_env()
    return f"https://graph.facebook.com/{version}"


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _raise_for_response(response: httpx.Response, *, action: str) -> None:
    if response.status_code < 400:
        return
    logger.warning(
        "Meta template API failed",
        extra={"action": action, "status_code": response.status_code, "body": response.text[:500]},
    )
    raise MetaTemplateApiError(
        f"Meta template API {action} failed {response.status_code}: {response.text[:500]}"
    )


def download_header_image(*, url: str, timeout: float = 60.0) -> tuple[bytes, str]:
    cleaned = url.strip()
    if not cleaned:
        raise MetaTemplateApiError("header image URL missing")
    try:
        response = httpx.get(cleaned, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise MetaTemplateApiError(f"header image download failed: {exc}") from exc
    _raise_for_response(response, action="download header image")
    mime_type = (response.headers.get("content-type") or "image/png").split(";")[0].strip()
    if not response.content:
        raise MetaTemplateApiError("header image download returned empty body")
    return response.content, mime_type or "image/png"


def _file_name_from_url(url: str, *, mime_type: str) -> str:
    path = urlparse(url).path.rsplit("/", 1)[-1].strip()
    if path:
        return path
    extension = "png" if mime_type == "image/png" else "jpg"
    return f"whatsapp-header.{extension}"


def upload_template_header_handle(
    *,
    app_id: str,
    access_token: str,
    file_bytes: bytes,
    mime_type: str,
    file_name: str | None = None,
) -> str:
    if not app_id or not access_token:
        raise MetaTemplateApiError("Meta app_id and access_token are required for header upload")
    if not file_bytes:
        raise MetaTemplateApiError("header image bytes missing")

    resolved_name = (file_name or _file_name_from_url("", mime_type=mime_type)).strip()
    base = _graph_base_url()
    try:
        session_response = httpx.post(
            f"{base}/{app_id}/uploads",
            params={
                "file_name": resolved_name,
                "file_length": str(len(file_bytes)),
                "file_type": mime_type,
                "access_token": access_token,
            },
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        raise MetaTemplateApiError(f"Meta upload session failed: {exc}") from exc
    _raise_for_response(session_response, action="create upload session")

    session_data = session_response.json()
    if not isinstance(session_data, dict):
        raise MetaTemplateApiError("Meta upload session returned non-object JSON")
    session_id = str(session_data.get("id") or "").strip()
    if not session_id:
        raise MetaTemplateApiError("Meta upload session missing id")

    try:
        upload_response = httpx.post(
            f"{base}/{session_id}",
            content=file_bytes,
            headers={
                **_auth_headers(access_token),
                "file_offset": "0",
            },
            timeout=120.0,
        )
    except httpx.HTTPError as exc:
        raise MetaTemplateApiError(f"Meta upload binary failed: {exc}") from exc
    _raise_for_response(upload_response, action="upload header binary")

    upload_data = upload_response.json()
    if not isinstance(upload_data, dict):
        raise MetaTemplateApiError("Meta upload binary returned non-object JSON")
    handle = str(upload_data.get("h") or "").strip()
    if not handle:
        raise MetaTemplateApiError("Meta upload binary missing handle (h)")
    return handle


def upload_template_header_from_url(
    *,
    app_id: str,
    access_token: str,
    image_url: str,
) -> str:
    file_bytes, mime_type = download_header_image(url=image_url)
    file_name = _file_name_from_url(image_url, mime_type=mime_type)
    return upload_template_header_handle(
        app_id=app_id,
        access_token=access_token,
        file_bytes=file_bytes,
        mime_type=mime_type,
        file_name=file_name,
    )


def list_message_templates(
    *,
    waba_id: str,
    access_token: str,
    name: str | None = None,
) -> list[dict[str, Any]]:
    if not waba_id or not access_token:
        raise MetaTemplateApiError("WABA id and access_token are required")

    params: dict[str, str] = {
        "fields": "name,status,language,category,id",
        "limit": "100",
    }
    if name:
        params["name"] = name

    items: list[dict[str, Any]] = []
    url = f"{_graph_base_url()}/{waba_id}/message_templates"
    next_url: str | None = url
    next_params: dict[str, str] | None = params

    while next_url:
        try:
            response = httpx.get(
                next_url,
                params=next_params,
                headers=_auth_headers(access_token),
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            raise MetaTemplateApiError(f"list templates failed: {exc}") from exc
        _raise_for_response(response, action="list templates")

        data = response.json()
        if not isinstance(data, dict):
            raise MetaTemplateApiError("list templates returned non-object JSON")
        for item in data.get("data") or []:
            if isinstance(item, dict):
                items.append(item)

        paging = data.get("paging") if isinstance(data.get("paging"), dict) else {}
        next_url = str(paging.get("next") or "").strip() or None
        next_params = None

    return items


def find_message_template(
    *,
    waba_id: str,
    access_token: str,
    name: str,
    language: str,
) -> dict[str, Any] | None:
    try:
        items = list_message_templates(waba_id=waba_id, access_token=access_token, name=name)
    except MetaTemplateApiError as exc:
        logger.warning("list templates failed name=%s: %s", name, exc)
        return None

    for item in items:
        if str(item.get("name") or "").strip() == name and str(item.get("language") or "").strip() == language:
            return item
    return None


def create_message_template(
    *,
    waba_id: str,
    access_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not waba_id or not access_token:
        raise MetaTemplateApiError("WABA id and access_token are required")

    try:
        response = httpx.post(
            f"{_graph_base_url()}/{waba_id}/message_templates",
            json=payload,
            headers={**_auth_headers(access_token), "Content-Type": "application/json"},
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        raise MetaTemplateApiError(f"create template failed: {exc}") from exc
    _raise_for_response(response, action="create template")

    data = response.json()
    if not isinstance(data, dict):
        raise MetaTemplateApiError("create template returned non-object JSON")
    return data
