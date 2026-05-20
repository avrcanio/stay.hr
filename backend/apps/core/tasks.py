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
