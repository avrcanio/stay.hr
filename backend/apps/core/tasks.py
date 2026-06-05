from celery import shared_task


@shared_task
def ping() -> str:
    return "pong"


@shared_task
def send_push_notification(
    token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> str:
    from apps.core.firebase import send_fcm_message

    return send_fcm_message(token=token, title=title, body=body, data=data)


@shared_task
def notify_new_reservation(reservation_id: int) -> dict:
    from apps.core.notifications import send_tenant_reception_push
    from apps.core.push_payload import reception_push_data
    from apps.reservations.models import Reservation

    reservation = (
        Reservation.objects.select_related("tenant", "property")
        .filter(pk=reservation_id)
        .first()
    )
    if reservation is None:
        return {"sent": 0, "reservation_id": reservation_id, "reason": "not_found"}

    check_in = reservation.check_in.isoformat()
    booking_code = reservation.booking_code or str(reservation.pk)
    title = "Nova rezervacija"
    body = f"{reservation.booker_name} · dolazak {check_in}"
    if reservation.property_id:
        body = f"{reservation.booker_name} · {reservation.property.name} · {check_in}"

    summary = f"{reservation.booker_name} · dolazak {check_in}"
    data = reception_push_data(
        event_type="reservation.created",
        reservation_id=reservation.pk,
        summary=summary,
        booking_code=booking_code,
        check_in=check_in,
        check_out=reservation.check_out.isoformat(),
        status=reservation.status,
        tenant_id=str(reservation.tenant_id),
    )

    message_ids = send_tenant_reception_push(
        tenant_id=reservation.tenant_id,
        title=title,
        body=body,
        data=data,
    )
    return {
        "sent": len(message_ids),
        "reservation_id": reservation_id,
        "message_ids": message_ids,
    }


@shared_task
def notify_reservation_status_changed(
    reservation_id: int,
    old_status: str,
    new_status: str,
    origin_installation_id: str = "",
) -> dict:
    from apps.core.notifications import send_tenant_reception_push
    from apps.core.push_payload import reception_push_data
    from apps.reservations.models import Reservation

    reservation = (
        Reservation.objects.select_related("tenant", "property")
        .filter(pk=reservation_id)
        .first()
    )
    if reservation is None:
        return {"sent": 0, "reservation_id": reservation_id, "reason": "not_found"}

    if old_status == new_status:
        return {"sent": 0, "reservation_id": reservation_id, "reason": "unchanged"}

    title = "Promjena statusa"
    body = f"{reservation.booker_name} · {old_status} → {new_status}"
    if reservation.property_id:
        body = f"{reservation.booker_name} · {reservation.property.name} · {old_status} → {new_status}"

    summary = f"{old_status} → {new_status}"
    data = reception_push_data(
        event_type="reservation.status_changed",
        reservation_id=reservation.pk,
        origin_installation_id=origin_installation_id,
        summary=summary,
        status=new_status,
        tenant_id=str(reservation.tenant_id),
    )

    message_ids = send_tenant_reception_push(
        tenant_id=reservation.tenant_id,
        title=title,
        body=body,
        data=data,
    )
    return {
        "sent": len(message_ids),
        "reservation_id": reservation_id,
        "message_ids": message_ids,
    }


_GUEST_MESSAGE_CHANNEL_LABELS = {
    "booking": "Booking.com",
    "whatsapp": "WhatsApp",
}


def _truncate_preview(text: str, *, limit: int = 100) -> str:
    snippet = (text or "").strip()
    if len(snippet) <= limit:
        return snippet
    return snippet[: limit - 3] + "..."


def _guest_message_push_body(
    reservation,
    *,
    channel: str,
    body_preview: str,
) -> tuple[str, str]:
    channel_label = _GUEST_MESSAGE_CHANNEL_LABELS.get(channel, channel)
    name = reservation.booker_name or reservation.booking_code or str(reservation.pk)
    snippet = _truncate_preview(body_preview)
    if snippet:
        body = f"{name} · {channel_label}: {snippet}"
    else:
        body = f"{name} · {channel_label}"
    return body, snippet


@shared_task
def notify_guest_message_inbound(
    reservation_id: int,
    *,
    channel: str,
    body_preview: str = "",
) -> dict:
    from apps.core.notifications import send_tenant_reception_push
    from apps.core.push_payload import reception_push_data
    from apps.reservations.models import Reservation

    reservation = (
        Reservation.objects.select_related("tenant", "property")
        .filter(pk=reservation_id)
        .first()
    )
    if reservation is None:
        return {"sent": 0, "reservation_id": reservation_id, "reason": "not_found"}

    preview = (body_preview or "").strip()
    if not preview and channel != "whatsapp":
        return {"sent": 0, "reservation_id": reservation_id, "reason": "empty_preview"}

    title = "Nova poruka"
    body, summary = _guest_message_push_body(
        reservation,
        channel=channel,
        body_preview=preview or "Poruka (WhatsApp)",
    )
    booking_code = reservation.booking_code or str(reservation.pk)
    data = reception_push_data(
        event_type="guest.message.received",
        reservation_id=reservation.pk,
        summary=summary or preview,
        booking_code=booking_code,
        channel=channel,
        tenant_id=str(reservation.tenant_id),
    )

    message_ids = send_tenant_reception_push(
        tenant_id=reservation.tenant_id,
        title=title,
        body=body,
        data=data,
    )
    return {
        "sent": len(message_ids),
        "reservation_id": reservation_id,
        "channel": channel,
        "message_ids": message_ids,
    }


def _auto_checkout_skipped_body(count: int, booking_codes: list[str]) -> str:
    if count == 1:
        base = "1 rezervacija nije odjavljena (eVisitor)"
    elif 2 <= count <= 4:
        base = f"{count} rezervacije nisu odjavljene (eVisitor)"
    else:
        base = f"{count} rezervacija nije odjavljena (eVisitor)"

    if not booking_codes:
        return base

    shown = booking_codes[:5]
    suffix = ", ".join(shown)
    if count > len(shown):
        suffix = f"{suffix} (+{count - len(shown)})"
    return f"{base}: {suffix}"


@shared_task
def notify_auto_checkout_summary(tenant_id: int, skipped: list[dict]) -> dict:
    import json

    from apps.core.notifications import send_tenant_reception_push
    from apps.core.push_payload import reception_push_data

    count = len(skipped)
    if count == 0:
        return {"sent": 0, "tenant_id": tenant_id, "reason": "empty"}

    booking_codes = [
        str(item.get("booking_code") or "")
        for item in skipped
        if item.get("booking_code")
    ]
    title = "Auto odjava — preskočeno"
    body = _auto_checkout_skipped_body(count, booking_codes)
    data = reception_push_data(
        event_type="auto_checkout.skipped",
        reservation_id=0,
        summary=f"{count} preskočeno",
        tenant_id=str(tenant_id),
        skipped_count=str(count),
        skipped=json.dumps(skipped),
    )

    message_ids = send_tenant_reception_push(
        tenant_id=tenant_id,
        title=title,
        body=body,
        data=data,
    )
    return {
        "sent": len(message_ids),
        "tenant_id": tenant_id,
        "skipped_count": count,
        "message_ids": message_ids,
    }
