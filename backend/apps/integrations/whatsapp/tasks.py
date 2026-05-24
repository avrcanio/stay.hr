from __future__ import annotations

import logging

from celery import shared_task

from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.client import WhatsAppApiError, send_text_message
from apps.integrations.whatsapp.reply import build_greeting
from apps.integrations.whatsapp.reservation_lookup import find_reservation_for_wa_id
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig

logger = logging.getLogger(__name__)


@shared_task
def process_inbound_message(message_id: int, *, profile_name: str = "") -> dict:
    row = (
        WhatsAppMessage.objects.select_related("integration", "tenant")
        .filter(pk=message_id, direction=WhatsAppMessage.Direction.INBOUND)
        .first()
    )
    if row is None:
        return {"status": "missing"}

    integration_row = row.integration
    if integration_row is None or not integration_row.is_active:
        return {"status": "no_integration"}

    runtime = WhatsAppRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    if not runtime.auto_reply:
        return {"status": "auto_reply_disabled"}

    if not runtime.access_token or not runtime.phone_number_id:
        logger.warning("WhatsApp auto-reply skipped: missing credentials tenant=%s", row.tenant_id)
        return {"status": "missing_credentials"}

    reservation = find_reservation_for_wa_id(tenant_id=row.tenant_id, wa_id=row.wa_id)
    greeting = build_greeting(
        integration_row=integration_row,
        reservation=reservation,
        profile_name=profile_name,
    )

    try:
        response = send_text_message(
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            to_wa_id=row.wa_id,
            body=greeting,
        )
    except WhatsAppApiError as exc:
        logger.warning("WhatsApp reply failed message_id=%s: %s", message_id, exc)
        return {"status": "send_failed", "detail": str(exc)}

    outbound_wamid = _extract_outbound_wamid(response)
    if outbound_wamid:
        WhatsAppMessage.objects.create(
            tenant_id=row.tenant_id,
            integration=integration_row,
            reservation=reservation,
            wamid=outbound_wamid,
            wa_id=row.wa_id,
            phone_number_id=runtime.phone_number_id,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            message_type="text",
            body=greeting,
            raw_payload=response,
        )

    if reservation is not None and row.reservation_id is None:
        row.reservation = reservation
        row.save(update_fields=["reservation"])

    return {
        "status": "replied",
        "reservation_id": reservation.pk if reservation else None,
        "outbound_wamid": outbound_wamid,
    }


def _extract_outbound_wamid(response: dict) -> str:
    for item in response.get("messages") or []:
        wamid = str(item.get("id") or "").strip()
        if wamid:
            return wamid
    return ""
