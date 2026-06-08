from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.communications.guest_compose import (
    HINT_AUTOCHECKIN_WHATSAPP_INTRO,
    autocheckin_wa_me_prefill,
    compose_language_for_reservation,
    render_autocheckin_whatsapp_intro_email,
    render_autocheckin_whatsapp_intro_email_html,
)
from apps.communications.guest_email import _guest_recipient
from apps.communications.guest_message_send import (
    build_wa_me_url,
    default_email_subject,
    send_guest_email_with_timeline_record,
)
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

DEFAULT_EMAIL_LEAD_MINUTES = 30


def is_immediate_autocheckin_eligible(reservation: Reservation) -> bool:
    """Same-day check-in when property autocheck-in time has passed (local time)."""
    return _is_due_for_autocheckin_welcome(reservation)


def _email_lead_minutes(prop: Property) -> int:
    lead = prop.whatsapp_autocheckin_email_lead_minutes
    if lead is None or lead <= 0:
        return DEFAULT_EMAIL_LEAD_MINUTES
    return int(lead)


def _in_intro_email_window(prop: Property, now: datetime) -> bool:
    lead = timedelta(minutes=_email_lead_minutes(prop))
    checkin_dt = datetime.combine(now.date(), prop.whatsapp_autocheckin_time, tzinfo=now.tzinfo)
    return (checkin_dt - lead) <= now < checkin_dt


def mark_autocheckin_engaged(reservation: Reservation) -> bool:
    if reservation.whatsapp_autocheckin_engaged_at is not None:
        return False
    reservation.whatsapp_autocheckin_engaged_at = timezone.now()
    reservation.save(update_fields=["whatsapp_autocheckin_engaged_at", "updated_at"])
    return True


def _build_intro_email_context(reservation: Reservation) -> tuple[str, str] | None:
    integration_row, runtime = get_active_whatsapp_integration(reservation.tenant)
    if integration_row is None or runtime is None:
        return None
    display_phone = (runtime.display_phone_number or "").strip()
    business_digits = normalize_phone(display_phone or runtime.phone_number_id)
    if not business_digits:
        return None
    lang = compose_language_for_reservation(reservation)
    prefill = autocheckin_wa_me_prefill(lang)
    wa_link = build_wa_me_url(business_digits, prefill)
    return wa_link, display_phone or business_digits


def send_autocheckin_intro_email(
    reservation: Reservation,
    *,
    dry_run: bool = False,
) -> dict:
    recipient = _guest_recipient(reservation)
    if not recipient:
        return {"status": "skipped", "reason": "no_email", "reservation_id": reservation.pk}

    ctx = _build_intro_email_context(reservation)
    if ctx is None:
        return {"status": "skipped", "reason": "no_whatsapp", "reservation_id": reservation.pk}

    wa_link, display_phone = ctx
    body = render_autocheckin_whatsapp_intro_email(
        reservation,
        wa_link=wa_link,
        display_phone=display_phone,
    )
    body_html = render_autocheckin_whatsapp_intro_email_html(
        reservation,
        wa_link=wa_link,
        display_phone=display_phone,
    )

    if dry_run:
        return {
            "status": "dry_run",
            "reservation_id": reservation.pk,
            "to": recipient,
            "wa_link": wa_link,
            "has_html": True,
        }

    with transaction.atomic():
        locked = (
            Reservation.objects.select_for_update()
            .filter(pk=reservation.pk)
            .first()
        )
        if locked is None:
            return {"status": "missing", "reservation_id": reservation.pk}
        if locked.whatsapp_autocheckin_intro_email_sent_at is not None:
            return {"status": "already_sent", "reservation_id": reservation.pk}

        subject = default_email_subject(locked)
        outbound = send_guest_email_with_timeline_record(
            locked,
            body,
            subject=subject,
            body_html=body_html,
            intent=GuestMessageIntent.CHECKIN,
            hint=HINT_AUTOCHECKIN_WHATSAPP_INTRO,
        )
        if outbound.status != GuestOutboundMessageStatus.SENT:
            return {
                "status": "send_failed",
                "reason": outbound.error_message or "send_failed",
                "reservation_id": reservation.pk,
            }

        sent_at = outbound.draft.sent_at or timezone.now()
        locked.whatsapp_autocheckin_intro_email_sent_at = sent_at
        locked.save(update_fields=["whatsapp_autocheckin_intro_email_sent_at", "updated_at"])

    return {"status": "sent", "reservation_id": reservation.pk, "to": recipient}


def iter_due_autocheckin_intro_emails(
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
        if not _in_intro_email_window(prop, now):
            continue

        qs = (
            Reservation.objects.filter(
                tenant_id=prop.tenant_id,
                property=prop,
                check_in=target_date,
                status=Reservation.Status.EXPECTED,
                whatsapp_autocheckin_intro_email_sent_at__isnull=True,
            )
            .exclude(booker_email="")
            .select_related("property", "tenant")
        )
        for reservation in qs:
            if _guest_recipient(reservation):
                reservations.append(reservation)
    return reservations


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

    if reservation.whatsapp_autocheckin_engaged_at is not None:
        return {"status": "skipped", "reason": "guest_engaged", "reservation_id": reservation.pk}

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


def guest_phone_number(reservation: Reservation) -> str:
    from apps.communications.guest_message_send import guest_phone_number as _gpn

    return _gpn(reservation)


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
                whatsapp_autocheckin_engaged_at__isnull=True,
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
        "intro_sent": 0,
        "intro_skipped": 0,
        "intro_failed": 0,
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "dry_run": False,
    }

    for reservation in iter_due_autocheckin_intro_emails():
        outcome = send_autocheckin_intro_email(reservation)
        status = outcome.get("status")
        if status == "sent":
            result["intro_sent"] += 1
        elif status == "send_failed":
            result["intro_failed"] += 1
        else:
            result["intro_skipped"] += 1

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
