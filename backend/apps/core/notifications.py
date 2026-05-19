"""Push notifications to Hospira reception devices."""

from __future__ import annotations

import logging

from apps.core.firebase import FirebaseNotConfiguredError, is_firebase_configured, send_fcm_message

logger = logging.getLogger(__name__)


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
