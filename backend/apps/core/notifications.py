"""Push notifications to Hospira reception devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from apps.core.firebase import is_firebase_configured, send_fcm_message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReceptionPushDecision:
    allowed: bool
    block_reason: str | None = None
    tenant_slug: str | None = None
    allowed_count: int = 0


def _normalized_push_tenant_slugs() -> frozenset[str]:
    slugs = settings.FCM_PUSH_ALLOWED_TENANT_SLUGS
    return frozenset(s.strip().lower() for s in slugs if s.strip())


def reception_push_allowed(*, tenant_id: int) -> ReceptionPushDecision:
    """
    Centralni filter — samo odluka, bez I/O osim slug lookupa.

    Decision order (guard + caller):

    1. FCM_PUSH_ENABLED — installation-level off → push_disabled
    2. FCM_PUSH_MAINTENANCE — temporary suppress delivery → maintenance_mode
    3. FCM_PUSH_ALLOWED_TENANT_SLUGS — tenant entitlement (fail-closed if empty)
    4. Firebase configuration / tokens — checked in send_tenant_reception_push after guard
    """
    allowed_slugs = _normalized_push_tenant_slugs()
    allowed_count = len(allowed_slugs)

    if not settings.FCM_PUSH_ENABLED:
        return ReceptionPushDecision(
            allowed=False,
            block_reason="push_disabled",
            allowed_count=allowed_count,
        )

    if settings.FCM_PUSH_MAINTENANCE:
        return ReceptionPushDecision(
            allowed=False,
            block_reason="maintenance_mode",
            allowed_count=allowed_count,
        )

    if not allowed_slugs:
        return ReceptionPushDecision(
            allowed=False,
            block_reason="allowlist_empty",
            allowed_count=0,
        )

    from apps.tenants.models import Tenant

    tenant_slug = (
        Tenant.objects.filter(pk=tenant_id).values_list("slug", flat=True).first()
    )
    if tenant_slug is None:
        return ReceptionPushDecision(
            allowed=False,
            block_reason="tenant_not_found",
            allowed_count=allowed_count,
        )

    normalized_slug = tenant_slug.strip().lower()
    if normalized_slug not in allowed_slugs:
        return ReceptionPushDecision(
            allowed=False,
            block_reason="tenant_not_allowed",
            tenant_slug=normalized_slug,
            allowed_count=allowed_count,
        )

    return ReceptionPushDecision(
        allowed=True,
        tenant_slug=normalized_slug,
        allowed_count=allowed_count,
    )


def tenant_fcm_tokens(tenant_id: int) -> list[str]:
    from apps.tenants.models import ApiApplication

    return list(
        ApiApplication.objects.filter(
            tenant_id=tenant_id,
            is_active=True,
        )
        .exclude(fcm_token="")
        .values_list("fcm_token", flat=True)
    )


def send_tenant_reception_push(
    *,
    tenant_id: int,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> list[str]:
    """
    Send the same push notification to all registered FCM tokens for a tenant.
    Returns FCM message IDs for successful sends.
    """
    decision = reception_push_allowed(tenant_id=tenant_id)
    if not decision.allowed:
        logger.info(
            "Skipping push tenant_id=%s reason=%s tenant_slug=%s allowed_count=%s",
            tenant_id,
            decision.block_reason,
            decision.tenant_slug,
            decision.allowed_count,
        )
        return []

    if not is_firebase_configured():
        logger.info("Skipping push (Firebase not configured) tenant_id=%s", tenant_id)
        return []

    tokens = tenant_fcm_tokens(tenant_id)
    if not tokens:
        logger.info("No FCM tokens registered for tenant_id=%s", tenant_id)
        return []

    message_ids: list[str] = []
    for token in tokens:
        try:
            message_id = send_fcm_message(
                token=token,
                title=title,
                body=body,
                data=data,
            )
            message_ids.append(message_id)
        except Exception:
            logger.exception("FCM send failed tenant_id=%s", tenant_id)
    return message_ids
