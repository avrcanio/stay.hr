from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

from apps.tenants.models import StaffLoginEvent, Tenant

User = get_user_model()
logger = logging.getLogger(__name__)


def client_ip_from_request(request) -> str | None:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    return remote or None


def user_agent_from_request(request) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:255]


def record_staff_login_event(
    *,
    user: User | None,
    username: str,
    channel: str,
    tenant: Tenant | None = None,
    request,
) -> StaffLoginEvent:
    event = StaffLoginEvent.objects.create(
        user=user,
        username=username,
        tenant=tenant,
        channel=channel,
        ip_address=client_ip_from_request(request),
        user_agent=user_agent_from_request(request),
    )
    logger.info(
        "staff_login",
        extra={
            "username": username,
            "user_id": user.pk if user else None,
            "tenant_id": tenant.pk if tenant else None,
            "tenant_slug": tenant.slug if tenant else None,
            "channel": channel,
            "ip_address": event.ip_address,
        },
    )
    return event
