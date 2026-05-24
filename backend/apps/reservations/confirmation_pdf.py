from django.urls import reverse

from apps.reservations.models import Reservation


def reservation_confirmation_pdf_url(reservation: Reservation, request) -> str:
    if not reservation.confirmation_pdf:
        return ""
    return request.build_absolute_uri(
        reverse(
            "reception-reservation-confirmation-pdf",
            kwargs={"pk": reservation.pk},
        )
    )
