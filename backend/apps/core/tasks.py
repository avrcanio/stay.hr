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
    # Unused in codebase; if ever called, route through send_tenant_reception_push instead.
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
    "email": "Email",
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


@shared_task
def notify_guest_review_inbound(
    reservation_id: int,
    *,
    review_id: int,
    ota: str = "",
    score_preview: str = "",
    content_preview: str = "",
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

    name = reservation.booker_name or reservation.booking_code or str(reservation.pk)
    ota_label = ota or "OTA"
    preview = _truncate_preview(content_preview)
    if score_preview:
        score_part = f" · {score_preview}/10"
    else:
        score_part = ""
    if preview:
        body = f"{name} · {ota_label}{score_part}: {preview}"
        summary = preview
    else:
        body = f"{name} · nova recenzija ({ota_label}{score_part})"
        summary = f"Recenzija {ota_label}{score_part}".strip()

    booking_code = reservation.booking_code or str(reservation.pk)
    data = reception_push_data(
        event_type="guest.review.received",
        reservation_id=reservation.pk,
        summary=summary,
        booking_code=booking_code,
        channel="booking",
        tenant_id=str(reservation.tenant_id),
    )
    data["review_id"] = str(review_id)

    message_ids = send_tenant_reception_push(
        tenant_id=reservation.tenant_id,
        title="Nova recenzija",
        body=body,
        data=data,
    )
    return {
        "sent": len(message_ids),
        "reservation_id": reservation_id,
        "review_id": review_id,
        "message_ids": message_ids,
    }


def _primary_reservation_id_from_skipped(skipped: list[dict]) -> int:
    for item in skipped:
        reservation_id = int(item.get("reservation_id") or 0)
        if reservation_id > 0:
            return reservation_id
    return 0


def _auto_checkout_skipped_body(count: int, skipped: list[dict]) -> str:
    if count == 1:
        item = skipped[0]
        reservation_id = int(item.get("reservation_id") or 0)
        booking_code = str(item.get("booking_code") or reservation_id or "").strip()
        if reservation_id > 0 and booking_code:
            return f"1 rezervacija nije odjavljena (eVisitor): #{reservation_id} · {booking_code}"
        return "1 rezervacija nije odjavljena (eVisitor)"

    if 2 <= count <= 4:
        base = f"{count} rezervacije nisu odjavljene (eVisitor)"
    else:
        base = f"{count} rezervacija nije odjavljena (eVisitor)"

    labels: list[str] = []
    for item in skipped[:5]:
        reservation_id = int(item.get("reservation_id") or 0)
        booking_code = str(item.get("booking_code") or reservation_id or "").strip()
        if reservation_id > 0 and booking_code:
            labels.append(f"#{reservation_id} · {booking_code}")
        elif booking_code:
            labels.append(booking_code)

    if not labels:
        return base

    suffix = ", ".join(labels)
    if count > len(labels):
        suffix = f"{suffix} (+{count - len(labels)})"
    return f"{base}: {suffix}"


@shared_task
def notify_auto_checkout_summary(tenant_id: int, skipped: list[dict]) -> dict:
    import json

    from apps.core.notifications import send_tenant_reception_push
    from apps.core.push_payload import reception_push_data

    count = len(skipped)
    if count == 0:
        return {"sent": 0, "tenant_id": tenant_id, "reason": "empty"}

    primary_reservation_id = _primary_reservation_id_from_skipped(skipped)
    title = "Auto odjava — preskočeno"
    body = _auto_checkout_skipped_body(count, skipped)
    summary = body if count == 1 else f"{count} preskočeno"
    data = reception_push_data(
        event_type="auto_checkout.skipped",
        reservation_id=primary_reservation_id,
        summary=summary,
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
