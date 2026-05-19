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
    from apps.reservations.models import Reservation

    from apps.core.notifications import send_tenant_reception_push

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

    data = {
        "event": "reservation_created",
        "reservation_id": str(reservation.pk),
        "booking_code": booking_code,
        "check_in": check_in,
        "check_out": reservation.check_out.isoformat(),
        "status": reservation.status,
        "tenant_id": str(reservation.tenant_id),
    }

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
