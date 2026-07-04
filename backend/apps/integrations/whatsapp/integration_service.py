from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
import httpx

from apps.integrations.models import IntegrationConfig
from apps.integrations.whatsapp.config import api_version_from_env
from apps.integrations.whatsapp.integration_lookup import resolve_whatsapp_integration
from apps.integrations.whatsapp.meta_templates import (
    MetaTemplateApiError,
    create_message_template,
    list_message_templates,
)

logger = logging.getLogger(__name__)

_INTEGRATION_CACHE_TTL = 15 * 60
_TEMPLATES_CACHE_TTL = 5 * 60


def _graph_base() -> str:
    return f"https://graph.facebook.com/{api_version_from_env()}"


def embedded_signup_supported() -> bool:
    return bool(getattr(settings, "META_APP_ID", "") and getattr(settings, "WHATSAPP_APP_SECRET", ""))


def get_whatsapp_integration_status(*, tenant) -> dict[str, Any]:
    cache_key = f"whatsapp:integration:status:{tenant.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    integration, runtime = resolve_whatsapp_integration(tenant)
    if integration is None or runtime is None:
        payload = {
            "connected": False,
            "embedded_signup_supported": embedded_signup_supported(),
            "business_verified": None,
            "display_name": "",
            "phone_number": "",
            "waba_id": "",
            "quality_rating": "",
            "messaging_limit": None,
            "using_platform_fallback": False,
            "fetched_at": timezone.now().isoformat(),
        }
        cache.set(cache_key, payload, _INTEGRATION_CACHE_TTL)
        return payload

    using_platform_fallback = integration.tenant_id != tenant.pk

    payload: dict[str, Any] = {
        "connected": runtime.can_send_messages(),
        "embedded_signup_supported": embedded_signup_supported(),
        "business_verified": None,
        "display_name": "",
        "phone_number": runtime.display_phone_number,
        "waba_id": runtime.effective_waba_id(),
        "quality_rating": "",
        "messaging_limit": None,
        "using_platform_fallback": using_platform_fallback,
        "fetched_at": timezone.now().isoformat(),
    }

    waba_id = runtime.effective_waba_id()
    if waba_id and runtime.access_token:
        try:
            response = httpx.get(
                f"{_graph_base()}/{waba_id}",
                params={"fields": "name,business_verification_status"},
                headers={"Authorization": f"Bearer {runtime.access_token}"},
                timeout=30.0,
            )
            if response.status_code < 400:
                data = response.json()
                if isinstance(data, dict):
                    payload["display_name"] = str(data.get("name") or payload["display_name"])
                    bv = str(data.get("business_verification_status") or "").lower()
                    payload["business_verified"] = bv in ("verified", "approved") if bv else None
        except httpx.HTTPError as exc:
            logger.warning("WABA status fetch failed tenant=%s: %s", tenant.pk, exc)

    if runtime.phone_number_id and runtime.access_token:
        try:
            response = httpx.get(
                f"{_graph_base()}/{runtime.phone_number_id}",
                params={"fields": "display_phone_number,quality_rating,messaging_limit_tier"},
                headers={"Authorization": f"Bearer {runtime.access_token}"},
                timeout=30.0,
            )
            if response.status_code < 400:
                data = response.json()
                if isinstance(data, dict):
                    payload["phone_number"] = str(
                        data.get("display_phone_number") or payload["phone_number"]
                    )
                    payload["quality_rating"] = str(data.get("quality_rating") or "")
                    tier = data.get("messaging_limit_tier")
                    if tier is not None:
                        payload["messaging_limit"] = tier
        except httpx.HTTPError as exc:
            logger.warning("phone status fetch failed tenant=%s: %s", tenant.pk, exc)

    cache.set(cache_key, payload, _INTEGRATION_CACHE_TTL)
    return payload


def exchange_oauth_code(*, code: str) -> str:
    app_id = getattr(settings, "META_APP_ID", "")
    app_secret = getattr(settings, "WHATSAPP_APP_SECRET", "")
    if not app_id or not app_secret:
        raise ValueError("meta_oauth_not_configured")
    response = httpx.get(
        f"{_graph_base()}/oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
        },
        timeout=30.0,
    )
    if response.status_code >= 400:
        raise ValueError(f"oauth_exchange_failed: {response.text[:300]}")
    data = response.json()
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise ValueError("oauth_exchange_missing_token")
    return token


def upsert_whatsapp_integration(
    *,
    tenant,
    waba_id: str,
    phone_number_id: str,
    display_phone_number: str = "",
) -> IntegrationConfig:
    row = IntegrationConfig.objects.filter(
        tenant=tenant,
        provider=IntegrationConfig.Provider.WHATSAPP,
        property__isnull=True,
    ).first()
    config = {
        "waba_id": waba_id,
        "phone_number_id": phone_number_id,
        "display_phone_number": display_phone_number,
    }
    if row is None:
        row = IntegrationConfig.objects.create(
            tenant=tenant,
            provider=IntegrationConfig.Provider.WHATSAPP,
            routing_key=phone_number_id,
            is_active=True,
        )
    else:
        row.routing_key = phone_number_id
        row.is_active = True
    existing = row.get_config_dict()
    existing.update(config)
    for legacy_key in ("access_token", "provider", "api_base_url"):
        existing.pop(legacy_key, None)
    row.set_config_dict(existing)
    row.save()
    cache.delete(f"whatsapp:integration:status:{tenant.pk}")
    cache.delete(f"whatsapp:templates:{tenant.pk}")
    return row


def list_cached_templates(*, tenant, live: bool = False) -> dict[str, Any]:
    cache_key = f"whatsapp:templates:{tenant.pk}"
    if not live:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    return sync_templates_from_meta(tenant=tenant)


def sync_templates_from_meta(*, tenant) -> dict[str, Any]:
    integration, runtime = resolve_whatsapp_integration(tenant)
    waba_id = runtime.effective_waba_id() if runtime else ""
    if integration is None or runtime is None or not waba_id:
        raise ValueError("whatsapp_templates_require_waba_id")
    templates = list_message_templates(
        waba_id=waba_id,
        access_token=runtime.access_token,
    )
    payload = {
        "templates": templates,
        "synced_at": timezone.now().isoformat(),
    }
    cache.set(f"whatsapp:templates:{tenant.pk}", payload, _TEMPLATES_CACHE_TTL)
    return payload


def create_whatsapp_template(
    *,
    tenant,
    payload: dict[str, Any],
) -> dict[str, Any]:
    integration, runtime = resolve_whatsapp_integration(tenant)
    waba_id = runtime.effective_waba_id() if runtime else ""
    if integration is None or runtime is None or not waba_id:
        raise ValueError("whatsapp_templates_require_waba_id")
    result = create_message_template(
        waba_id=waba_id,
        access_token=runtime.access_token,
        payload=payload,
    )
    cache.delete(f"whatsapp:templates:{tenant.pk}")
    return result
