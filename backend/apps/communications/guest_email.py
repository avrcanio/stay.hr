"""Send guest-facing booking emails."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from apps.reservations.models import Reservation, ReservationUnit
from apps.reservations.reservation_units import joined_room_names
from apps.tenants.models import TenantReceptionSettings

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


def _email_context(reservation: Reservation) -> dict:
    units = list(
        ReservationUnit.objects.filter(reservation=reservation).select_related("unit")
    )
    room_label = joined_room_names(reservation) if units else ""
    if not room_label and units:
        room_label = units[0].room_name or (units[0].unit.code if units[0].unit else "")

    return {
        "booker_name": reservation.booker_name,
        "booking_code": reservation.booking_code,
        "check_in": reservation.check_in.isoformat(),
        "check_out": reservation.check_out.isoformat(),
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


def send_booking_confirmed_email(reservation_id: int) -> dict:
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
            "booking confirmed email skipped: no recipient",
            extra={"reservation_id": reservation_id},
        )
        return {"sent": False, "reason": "no_recipient"}

    lang = _language_for_reservation(reservation)
    template_base = f"communications/email/booking_confirmed_{lang}"
    context = _email_context(reservation)
    subject = render_to_string(f"{template_base}_subject.txt", context).strip()
    body_text = render_to_string(f"{template_base}.txt", context)
    body_html = render_to_string(f"{template_base}.html", context)

    from_header, reply_to = _sender_for_reservation(reservation)
    message = EmailMultiAlternatives(
        subject=subject,
        body=body_text,
        from_email=from_header,
        to=[recipient],
        reply_to=[reply_to] if reply_to else None,
    )
    message.attach_alternative(body_html, "text/html")
    message.send(fail_silently=False)
    logger.info(
        "booking confirmed email sent",
        extra={"reservation_id": reservation_id, "to": recipient},
    )
    return {"sent": True, "to": recipient}


def send_booking_refused_email(reservation_id: int, *, reason: str = "") -> dict:
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
            "booking refused email skipped: no recipient",
            extra={"reservation_id": reservation_id},
        )
        return {"sent": False, "reason": "no_recipient"}

    lang = _language_for_reservation(reservation)
    template_base = f"communications/email/booking_refused_{lang}"
    context = {**_email_context(reservation), "reason": reason}
    subject = render_to_string(f"{template_base}_subject.txt", context).strip()
    body_text = render_to_string(f"{template_base}.txt", context)
    body_html = render_to_string(f"{template_base}.html", context)

    from_header, reply_to = _sender_for_reservation(reservation)
    message = EmailMultiAlternatives(
        subject=subject,
        body=body_text,
        from_email=from_header,
        to=[recipient],
        reply_to=[reply_to] if reply_to else None,
    )
    message.attach_alternative(body_html, "text/html")
    message.send(fail_silently=False)
    logger.info(
        "booking refused email sent",
        extra={"reservation_id": reservation_id, "to": recipient},
    )
    return {"sent": True, "to": recipient}
