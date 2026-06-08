from __future__ import annotations

import logging
from datetime import date

from celery import shared_task
from django.utils import timezone

from apps.communications.guest_message_send import guest_phone_number
from apps.communications.models import (
    GuestMessageChannel,
    GuestMessageDraft,
    GuestMessageIntent,
    GuestOutboundMessage,
    GuestOutboundMessageStatus,
)
from apps.core.timezone import property_local_now
from apps.integrations.models import IntegrationConfig, WhatsAppMessage
from apps.integrations.whatsapp.client import (
    WhatsAppApiError,
    extract_outbound_wamid,
    send_template_message,
)
from apps.integrations.whatsapp.integration_lookup import get_active_whatsapp_integration
from apps.integrations.whatsapp.phone import normalize_phone
from apps.integrations.whatsapp.welcome_template import (
    build_welcome_template_parameters,
    welcome_header_image_url,
    welcome_template_name,
)
from apps.properties.models import Property
from apps.reservations.models import Reservation

logger = logging.getLogger(__name__)


def is_immediate_autocheckin_eligible(reservation: Reservation) -> bool:
    """Same-day check-in when property autocheck-in time has passed (local time)."""
    return _is_due_for_autocheckin_welcome(reservation)


def _is_due_for_autocheckin_welcome(reservation: Reservation, *, on_date: date | None = None) -> bool:
    prop = reservation.property
    if not prop.whatsapp_autocheckin_enabled:
        return False
    now = property_local_now(prop)
    target_date = on_date or now.date()
    if reservation.check_in != target_date:
        return False
    if on_date is not None and on_date != now.date():
        return now.time() >= prop.whatsapp_autocheckin_time
    return now.time() >= prop.whatsapp_autocheckin_time


def send_welcome_template_for_reservation(
    reservation: Reservation,
    *,
    dry_run: bool = False,
) -> dict:
    if reservation.whatsapp_welcome_sent_at is not None:
        return {"status": "already_sent", "reservation_id": reservation.pk}

    if reservation.status != Reservation.Status.EXPECTED:
        return {"status": "skipped", "reason": "not_expected", "reservation_id": reservation.pk}

    prop = reservation.property
    if not prop.whatsapp_autocheckin_enabled:
        return {"status": "skipped", "reason": "disabled", "reservation_id": reservation.pk}

    phone_raw = guest_phone_number(reservation)
    phone_wa = normalize_phone(phone_raw)
    if not phone_wa:
        return {"status": "skipped", "reason": "no_phone", "reservation_id": reservation.pk}

    integration_row, runtime = get_active_whatsapp_integration(reservation.tenant)
    if integration_row is None or runtime is None or not runtime.send_credentials_ok():
        return {"status": "skipped", "reason": "no_credentials", "reservation_id": reservation.pk}

    config = integration_row.get_config_dict()
    lang, body_params = build_welcome_template_parameters(reservation)
    template_name = welcome_template_name(config=config, lang=lang)
    header_url = welcome_header_image_url(config)

    if dry_run:
        return {
            "status": "dry_run",
            "reservation_id": reservation.pk,
            "template_name": template_name,
            "language": lang,
            "parameters": body_params,
            "to": phone_wa,
        }

    try:
        response = send_template_message(
            phone_number_id=runtime.phone_number_id,
            access_token=runtime.access_token,
            to_wa_id=phone_wa,
            template_name=template_name,
            language_code=lang,
            body_parameters=body_params,
            header_image_url=header_url,
            provider=runtime.provider,
            api_base_url=runtime.api_base_url,
        )
    except WhatsAppApiError as exc:
        logger.warning(
            "WhatsApp welcome template failed reservation_id=%s: %s",
            reservation.pk,
            exc,
        )
        return {"status": "send_failed", "detail": str(exc), "reservation_id": reservation.pk}

    sent_at = timezone.now()
    outbound_wamid = extract_outbound_wamid(response)
    body_preview = " | ".join(body_params)

    if outbound_wamid:
        WhatsAppMessage.objects.create(
            tenant_id=reservation.tenant_id,
            integration=integration_row,
            reservation=reservation,
            wamid=outbound_wamid,
            wa_id=phone_wa,
            phone_number_id=runtime.phone_number_id,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            message_type="template",
            body=body_preview,
            raw_payload=response,
        )

    draft = GuestMessageDraft.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        intent=GuestMessageIntent.WELCOME_TEMPLATE,
        hint="whatsapp autocheckin welcome",
        language=lang,
        llm_body_text=body_preview,
        final_body_text=body_preview,
        channel=GuestMessageChannel.WHATSAPP,
        sent_at=sent_at,
    )
    GuestOutboundMessage.objects.create(
        tenant_id=reservation.tenant_id,
        reservation=reservation,
        draft=draft,
        channel=GuestMessageChannel.WHATSAPP,
        body_text=body_preview,
        status=GuestOutboundMessageStatus.SENT,
        to_phone=phone_raw or phone_wa,
    )

    reservation.whatsapp_welcome_sent_at = sent_at
    reservation.save(update_fields=["whatsapp_welcome_sent_at", "updated_at"])

    return {"status": "sent", "reservation_id": reservation.pk, "wamid": outbound_wamid}


def iter_due_autocheckin_reservations(
    *,
    property_id: int | None = None,
    on_date: date | None = None,
) -> list[Reservation]:
    props = Property.objects.filter(whatsapp_autocheckin_enabled=True)
    if property_id is not None:
        props = props.filter(pk=property_id)

    reservations: list[Reservation] = []
    for prop in props.select_related("tenant"):
        now = property_local_now(prop)
        target_date = on_date or now.date()
        if on_date is None and now.time() < prop.whatsapp_autocheckin_time:
            continue

        qs = (
            Reservation.objects.filter(
                tenant_id=prop.tenant_id,
                property=prop,
                check_in=target_date,
                status=Reservation.Status.EXPECTED,
                whatsapp_welcome_sent_at__isnull=True,
            )
            .exclude(booker_phone="")
            .select_related("property", "tenant")
            .prefetch_related("guests")
        )
        for reservation in qs:
            if _is_due_for_autocheckin_welcome(reservation, on_date=on_date):
                integration_row, runtime = get_active_whatsapp_integration(reservation.tenant)
                if integration_row is None or runtime is None or not runtime.send_credentials_ok():
                    continue
                if not normalize_phone(guest_phone_number(reservation)):
                    continue
                reservations.append(reservation)
    return reservations


@shared_task
def maybe_send_immediate_autocheckin_welcome(reservation_id: int) -> dict:
    reservation = (
        Reservation.objects.select_related("property", "tenant")
        .filter(pk=reservation_id)
        .first()
    )
    if reservation is None:
        return {"status": "missing", "reservation_id": reservation_id}
    if not is_immediate_autocheckin_eligible(reservation):
        return {"status": "skipped", "reason": "not_eligible", "reservation_id": reservation_id}
    return send_welcome_template_for_reservation(reservation)


@shared_task
def run_whatsapp_autocheckin_welcome() -> dict:
    result: dict = {
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "dry_run": False,
    }

    for reservation in iter_due_autocheckin_reservations():
        outcome = send_welcome_template_for_reservation(reservation)
        status = outcome.get("status")
        if status == "sent":
            result["sent"] += 1
        elif status == "send_failed":
            result["failed"] += 1
        else:
            result["skipped"] += 1

    return result
