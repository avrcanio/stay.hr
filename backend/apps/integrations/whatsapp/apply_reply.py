from __future__ import annotations

import logging
import os

from django.utils import timezone

from apps.communications.guest_compose import render_checkin_ready_message
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestMessageIntent,
    GuestOutboundMessage,
    GuestOutboundMessageStatus,
)
from apps.integrations.models import WhatsAppMessage
from apps.integrations.whatsapp.client import WhatsAppApiError, extract_outbound_wamid, send_text_message
from apps.integrations.whatsapp.integration_lookup import get_active_whatsapp_integration
from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobSource

logger = logging.getLogger(__name__)


def document_apply_reply_enabled() -> bool:
    raw = os.getenv("WHATSAPP_DOCUMENT_APPLY_REPLY", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def maybe_send_document_apply_whatsapp_reply(
    job: DocumentIntakeJob,
    *,
    applied: list,
) -> dict:
    if not document_apply_reply_enabled():
        return {"status": "disabled"}
    if not applied:
        return {"status": "skipped", "reason": "nothing_applied"}
    if job.source != DocumentIntakeJobSource.WHATSAPP:
        return {"status": "skipped", "reason": "not_whatsapp_source"}
    if job.whatsapp_reply_sent:
        return {"status": "already_sent"}
    if job.reservation_id is None:
        return {"status": "skipped", "reason": "no_reservation"}
    if DocumentIntakeJob.objects.filter(
        reservation_id=job.reservation_id,
        source=DocumentIntakeJobSource.WHATSAPP,
        whatsapp_reply_sent=True,
    ).exclude(pk=job.pk).exists():
        return {"status": "already_sent", "reason": "reservation_reply_sent"}

    reservation = job.reservation
    wa_message = job.whatsapp_message
    wa_id = (wa_message.wa_id if wa_message else "").strip()
    if not wa_id:
        return {"status": "skipped", "reason": "no_wa_id"}

    integration_row, runtime = get_active_whatsapp_integration(reservation.tenant)
    if integration_row is None or runtime is None or not runtime.send_credentials_ok():
        return {"status": "skipped", "reason": "no_credentials"}

    body = render_checkin_ready_message(reservation)
    try:
        response = send_text_message(
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            to_wa_id=wa_id,
            body=body,
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppApiError as exc:
        logger.warning("WhatsApp document apply reply failed job_id=%s: %s", job.pk, exc)
        return {"status": "send_failed", "detail": str(exc)}

    outbound_wamid = extract_outbound_wamid(response)
    if outbound_wamid:
        WhatsAppMessage.objects.create(
            tenant_id=job.tenant_id,
            integration=integration_row,
            reservation=reservation,
            wamid=outbound_wamid,
            wa_id=wa_id,
            phone_number_id=runtime.phone_number_id,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            message_type="text",
            body=body,
            raw_payload=response,
        )

    draft = GuestMessageDraft.objects.create(
        tenant_id=job.tenant_id,
        reservation=reservation,
        intent=GuestMessageIntent.REPLY,
        hint="checkin ready",
        language="",
        llm_body_text=body,
        final_body_text=body,
        channel=GuestMessageChannel.WHATSAPP,
        sent_at=timezone.now(),
    )
    GuestOutboundMessage.objects.create(
        tenant_id=job.tenant_id,
        reservation=reservation,
        draft=draft,
        channel=GuestMessageChannel.WHATSAPP,
        body_text=body,
        status=GuestOutboundMessageStatus.SENT,
        to_phone=reservation.booker_phone or wa_id,
    )

    job.whatsapp_reply_sent = True
    job.save(update_fields=["whatsapp_reply_sent", "updated_at"])

    return {"status": "sent", "wamid": outbound_wamid}
