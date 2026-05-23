from celery import shared_task


@shared_task
def send_guest_booking_confirmed_email(reservation_id: int) -> dict:
    from apps.communications.guest_email import send_booking_confirmed_email

    return send_booking_confirmed_email(reservation_id)


@shared_task
def send_guest_booking_refused_email(reservation_id: int, reason: str = "") -> dict:
    from apps.communications.guest_email import send_booking_refused_email

    return send_booking_refused_email(reservation_id, reason=reason)
