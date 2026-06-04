"""Send guest-facing booking emails."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string

from apps.reservations.models import Reservation, ReservationUnit
from apps.reservations.reservation_units import joined_room_names
from apps.tenants.models import TenantReceptionSettings
from apps.tenants.smtp import smtp_host_for_email

logger = logging.getLogger(__name__)


def _guest_recipient(reservation: Reservation) -> str | None:
    email = (reservation.booker_email or "").strip()
    if email:
        return email
    primary = reservation.guests.filter(is_primary=True).first()
    if primary and (primary.email or "").strip():
        return primary.email.strip()
    return None


def _sender_for_reservation(reservation: Reservation) -> tuple[str, str]:
    settings_row = (
        TenantReceptionSettings.objects.filter(tenant_id=reservation.tenant_id).first()
    )
    from_email = ""
    from_name = ""
    if settings_row is not None:
        from_email = (settings_row.guest_contact_email or "").strip()
        from_name = (settings_row.guest_contact_name or "").strip()

    if not from_email:
        prop = reservation.property
        contact = prop.contact if isinstance(prop.contact, dict) else {}
        from_email = (contact.get("email") or "").strip()

    if not from_name:
        from_name = reservation.property.name or reservation.tenant.name

    if not from_email:
        from_email = settings.DEFAULT_FROM_EMAIL

    formatted = f"{from_name} <{from_email}>" if from_name else from_email
    return formatted, from_email


def _format_time_hm(value) -> str:
    return value.strftime("%H:%M")


def _stay_display_labels(reservation: Reservation) -> tuple[str, str]:
    prop = reservation.property
    lang = _language_for_reservation(reservation)
    check_in_time = _format_time_hm(prop.check_in_time)
    check_out_time = _format_time_hm(prop.check_out_time)
    if lang == "hr":
        return (
            f"{reservation.check_in.isoformat()} od {check_in_time}",
            f"{reservation.check_out.isoformat()} do {check_out_time}",
        )
    return (
        f"{reservation.check_in.isoformat()} from {check_in_time}",
        f"{reservation.check_out.isoformat()} until {check_out_time}",
    )


def _email_context(reservation: Reservation) -> dict:
    units = list(
        ReservationUnit.objects.filter(reservation=reservation).select_related("unit")
    )
    room_label = joined_room_names(reservation) if units else ""
    if not room_label and units:
        room_label = units[0].room_name or (units[0].unit.code if units[0].unit else "")

    check_in_display, check_out_display = _stay_display_labels(reservation)
    prop = reservation.property

    return {
        "booker_name": reservation.booker_name,
        "booking_code": reservation.booking_code,
        "check_in": reservation.check_in.isoformat(),
        "check_out": reservation.check_out.isoformat(),
        "check_in_display": check_in_display,
        "check_out_display": check_out_display,
        "check_in_time": _format_time_hm(prop.check_in_time),
        "check_out_time": _format_time_hm(prop.check_out_time),
        "property_name": reservation.property.name,
        "room_label": room_label,
        "currency": reservation.currency or "EUR",
        "amount": reservation.amount,
    }


def _language_for_reservation(reservation: Reservation) -> str:
    lang = (reservation.property.language or reservation.tenant.default_language or "hr").strip()
    base = lang.split("-")[0].lower() or "hr"
    if base not in ("hr", "en"):
        return "en"
    return base


def _reception_settings_for_reservation(
    reservation: Reservation,
) -> TenantReceptionSettings | None:
    return TenantReceptionSettings.objects.filter(tenant_id=reservation.tenant_id).first()


def _smtp_connection_for_reservation(reservation: Reservation):
    settings_row = _reception_settings_for_reservation(reservation)
    if settings_row is None:
        return None

    from_email = (settings_row.guest_contact_email or "").strip()
    if not from_email or not settings_row.has_guest_smtp_password:
        if settings.EMAIL_HOST and settings.EMAIL_HOST_USER:
            return get_connection(
                host=settings.EMAIL_HOST,
                port=settings.EMAIL_PORT,
                username=settings.EMAIL_HOST_USER,
                password=settings.EMAIL_HOST_PASSWORD,
                use_tls=settings.EMAIL_USE_TLS,
                use_ssl=settings.EMAIL_USE_SSL,
            )
        logger.warning(
            "guest email skipped: no tenant SMTP credentials",
            extra={"tenant_id": reservation.tenant_id, "reservation_id": reservation.pk},
        )
        return None

    smtp_host = smtp_host_for_email(from_email)
    if not smtp_host:
        logger.warning(
            "guest email skipped: invalid guest_contact_email",
            extra={"tenant_id": reservation.tenant_id, "from_email": from_email},
        )
        return None

    try:
        password = settings_row.get_guest_smtp_password()
    except Exception:
        logger.exception(
            "guest email skipped: cannot decrypt SMTP password",
            extra={"tenant_id": reservation.tenant_id},
        )
        return None

    return get_connection(
        host=smtp_host,
        port=settings.EMAIL_PORT,
        username=from_email,
        password=password,
        use_tls=settings.EMAIL_USE_TLS,
        use_ssl=settings.EMAIL_USE_SSL,
    )


def _send_guest_email(message: EmailMultiAlternatives, reservation: Reservation) -> bool:
    connection = _smtp_connection_for_reservation(reservation)
    if connection is None:
        return False
    message.connection = connection
    message.send(fail_silently=False)
    return True


def should_send_guest_canceled_email(old_status: str) -> bool:
    return old_status not in {
        Reservation.Status.CANCELED,
        Reservation.Status.REFUSED,
    }


def queue_guest_booking_canceled_email(reservation_id: int, *, old_status: str) -> None:
    if not should_send_guest_canceled_email(old_status):
        return
    from apps.communications.tasks import send_guest_booking_canceled_email

    send_guest_booking_canceled_email.delay(reservation_id)


def _send_templated_guest_email(
    reservation_id: int,
    *,
    template_base: str,
    log_event: str,
    extra_context: dict | None = None,
) -> dict:
    reservation = (
        Reservation.objects.select_related("tenant", "property")
        .prefetch_related("guests")
        .filter(pk=reservation_id)
        .first()
    )
    if reservation is None:
        return {"sent": False, "reason": "not_found"}

    recipient = _guest_recipient(reservation)
    if not recipient:
        logger.warning(
            "%s skipped: no recipient",
            log_event,
            extra={"reservation_id": reservation_id},
        )
        return {"sent": False, "reason": "no_recipient"}

    lang = _language_for_reservation(reservation)
    template_name = f"{template_base}_{lang}"
    context = {**_email_context(reservation), **(extra_context or {})}
    subject = render_to_string(f"communications/email/{template_name}_subject.txt", context).strip()
    body_text = render_to_string(f"communications/email/{template_name}.txt", context)
    body_html = render_to_string(f"communications/email/{template_name}.html", context)

    from_header, reply_to = _sender_for_reservation(reservation)
    message = EmailMultiAlternatives(
        subject=subject,
        body=body_text,
        from_email=from_header,
        to=[recipient],
        reply_to=[reply_to] if reply_to else None,
    )
    message.attach_alternative(body_html, "text/html")
    if not _send_guest_email(message, reservation):
        return {"sent": False, "reason": "smtp_not_configured"}
    logger.info(
        log_event,
        extra={"reservation_id": reservation_id, "to": recipient},
    )
    return {"sent": True, "to": recipient}


def send_booking_confirmed_email(reservation_id: int) -> dict:
    return _send_templated_guest_email(
        reservation_id,
        template_base="booking_confirmed",
        log_event="booking confirmed email sent",
    )


def send_booking_refused_email(reservation_id: int, *, reason: str = "") -> dict:
    return _send_templated_guest_email(
        reservation_id,
        template_base="booking_refused",
        log_event="booking refused email sent",
        extra_context={"reason": reason},
    )


def send_booking_canceled_email(reservation_id: int) -> dict:
    return _send_templated_guest_email(
        reservation_id,
        template_base="booking_canceled",
        log_event="booking canceled email sent",
    )
