from __future__ import annotations

import logging
import os

from django.utils import timezone

from apps.communications.guest_compose import (
    HINT_ID_MISSING_SIDES,
    render_checkin_automation_failed_message,
    render_checkin_partial_documents_message,
    render_checkin_ready_message,
    render_missing_id_sides_message,
)
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestMessageIntent,
    GuestOutboundMessage,
    GuestOutboundMessageStatus,
)
from apps.integrations.evisitor.eligibility import guest_requires_evisitor
from apps.integrations.models import WhatsAppMessage
from apps.integrations.whatsapp.client import WhatsAppApiError, extract_outbound_wamid, send_text_message
from apps.integrations.whatsapp.integration_lookup import get_active_whatsapp_integration
from apps.reservations.document_intake_sides import find_missing_id_sides
from apps.reservations.guest_slots import is_unfilled_guest
from apps.reservations.models import DocumentIntakeJob, DocumentIntakeJobSource, Guest, Reservation

logger = logging.getLogger(__name__)


def document_apply_reply_enabled() -> bool:
    raw = os.getenv("WHATSAPP_DOCUMENT_APPLY_REPLY", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def adult_guests_for_registration(reservation: Reservation) -> list[Guest]:
    guests = list(reservation.guests.all())
    adults = [
        guest
        for guest in guests
        if guest_requires_evisitor(guest, reference_date=reservation.check_in)
    ]
    if adults:
        return adults
    target = reservation.adults_count or 1
    if guests:
        return guests[:target]
    return []


def guest_is_registered(guest: Guest) -> bool:
    if not is_unfilled_guest(guest):
        return True
    return guest.id_documents.exists()


def all_adult_guests_registered(reservation: Reservation) -> bool:
    adults = adult_guests_for_registration(reservation)
    if not adults:
        return False
    return all(guest_is_registered(guest) for guest in adults)


def _send_whatsapp_text_reply(
    *,
    job: DocumentIntakeJob,
    body: str,
    intent: str,
    hint: str,
    mark_reply_sent: bool,
) -> dict:
    reservation = job.reservation
    wa_message = job.whatsapp_message
    wa_id = (wa_message.wa_id if wa_message else "").strip()
    if not wa_id:
        return {"status": "skipped", "reason": "no_wa_id"}

    integration_row, runtime = get_active_whatsapp_integration(reservation.tenant)
    if integration_row is None or runtime is None or not runtime.send_credentials_ok():
        return {"status": "skipped", "reason": "no_credentials"}

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
        logger.warning("WhatsApp apply reply failed job_id=%s: %s", job.pk, exc)
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
        intent=intent,
        hint=hint,
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

    if mark_reply_sent:
        job.whatsapp_reply_sent = True
        job.save(update_fields=["whatsapp_reply_sent", "updated_at"])

    return {"status": "sent", "wamid": outbound_wamid}


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
    if job.reservation_id is None:
        return {"status": "skipped", "reason": "no_reservation"}

    reservation = job.reservation

    missing_sides = find_missing_id_sides(reservation)
    if missing_sides:
        body = render_missing_id_sides_message(reservation, missing_sides)
        return _send_whatsapp_text_reply(
            job=job,
            body=body,
            intent=GuestMessageIntent.REPLY,
            hint=HINT_ID_MISSING_SIDES,
            mark_reply_sent=False,
        )

    if all_adult_guests_registered(reservation):
        if job.whatsapp_reply_sent:
            return {"status": "already_sent"}
        if DocumentIntakeJob.objects.filter(
            reservation_id=job.reservation_id,
            source=DocumentIntakeJobSource.WHATSAPP,
            whatsapp_reply_sent=True,
        ).exclude(pk=job.pk).exists():
            return {"status": "already_sent", "reason": "reservation_reply_sent"}
        body = render_checkin_ready_message(reservation)
        return _send_whatsapp_text_reply(
            job=job,
            body=body,
            intent=GuestMessageIntent.REPLY,
            hint="checkin ready",
            mark_reply_sent=True,
        )

    body = render_checkin_partial_documents_message(reservation)
    return _send_whatsapp_text_reply(
        job=job,
        body=body,
        intent=GuestMessageIntent.REPLY,
        hint="checkin partial documents",
        mark_reply_sent=False,
    )


def maybe_send_checkin_automation_failed_whatsapp_reply(job: DocumentIntakeJob) -> dict:
    if not document_apply_reply_enabled():
        return {"status": "disabled"}
    if job.source != DocumentIntakeJobSource.WHATSAPP:
        return {"status": "skipped", "reason": "not_whatsapp_source"}
    if job.reservation_id is None:
        return {"status": "skipped", "reason": "no_reservation"}
    if job.whatsapp_reply_sent:
        return {"status": "already_sent"}

    reservation = job.reservation
    body = render_checkin_automation_failed_message(reservation)
    return _send_whatsapp_text_reply(
        job=job,
        body=body,
        intent=GuestMessageIntent.REPLY,
        hint="checkin automation failed",
        mark_reply_sent=False,
    )
