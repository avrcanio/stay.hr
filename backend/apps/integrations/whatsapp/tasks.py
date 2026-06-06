from __future__ import annotations

import logging

from celery import shared_task

from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.client import WhatsAppApiError, extract_outbound_wamid, send_text_message
from apps.integrations.whatsapp.reply import build_greeting
from apps.integrations.whatsapp.document_intake_task import process_whatsapp_document_message
from apps.integrations.whatsapp.reservation_lookup import find_reservation_for_wa_id
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig

logger = logging.getLogger(__name__)

_WHATSAPP_NON_TEXT_PREVIEW = "Poruka (WhatsApp)"


def _inbound_body_preview(row: WhatsAppMessage) -> str:
    if row.message_type == "text":
        return row.body or ""
    return _WHATSAPP_NON_TEXT_PREVIEW


def _link_inbound_to_reservation(row: WhatsAppMessage) -> None:
    if row.reservation_id is not None:
        return
    reservation = find_reservation_for_wa_id(tenant_id=row.tenant_id, wa_id=row.wa_id)
    if reservation is None:
        return
    row.reservation = reservation
    row.save(update_fields=["reservation"])


def _maybe_send_auto_reply(
    *,
    row: WhatsAppMessage,
    integration_row: IntegrationConfig,
    runtime: WhatsAppRuntimeConfig,
    reservation,
    profile_name: str,
) -> dict:
    if not runtime.auto_reply:
        return {"status": "auto_reply_disabled"}

    if not runtime.send_credentials_ok():
        logger.warning("WhatsApp auto-reply skipped: missing credentials tenant=%s", row.tenant_id)
        return {"status": "missing_credentials"}

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
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppApiError as exc:
        logger.warning("WhatsApp reply failed message_id=%s: %s", row.pk, exc)
        return {"status": "send_failed", "detail": str(exc)}

    outbound_wamid = extract_outbound_wamid(response)
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

    return {
        "status": "replied",
        "outbound_wamid": outbound_wamid,
    }


def _maybe_notify_guest_message_inbound(row: WhatsAppMessage) -> None:
    if row.reservation_id is None:
        return

    from apps.core.tasks import notify_guest_message_inbound

    notify_guest_message_inbound.delay(
        row.reservation_id,
        channel="whatsapp",
        body_preview=_inbound_body_preview(row),
    )


@shared_task
def process_inbound_message(message_id: int, *, profile_name: str = "") -> dict:
    row = (
        WhatsAppMessage.objects.select_related("integration", "tenant", "reservation")
        .filter(pk=message_id, direction=WhatsAppMessage.Direction.INBOUND)
        .first()
    )
    if row is None:
        return {"status": "missing"}

    integration_row = row.integration
    if integration_row is None or not integration_row.is_active:
        return {"status": "no_integration"}

    _link_inbound_to_reservation(row)
    reservation = row.reservation

    if row.message_type in ("image", "document"):
        process_whatsapp_document_message.delay(row.pk)

    runtime = WhatsAppRuntimeConfig.from_integration_dict(integration_row.get_config_dict())
    reply_result = _maybe_send_auto_reply(
        row=row,
        integration_row=integration_row,
        runtime=runtime,
        reservation=reservation,
        profile_name=profile_name,
    )

    _maybe_notify_guest_message_inbound(row)

    return {
        **reply_result,
        "reservation_id": reservation.pk if reservation else None,
    }
