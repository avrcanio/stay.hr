from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.channex.ari_service import get_active_channex_integration
from apps.integrations.channex.exceptions import ChannexBookingIngestError
from apps.integrations.channex.message_service import send_message_for_reservation
from apps.reservations.models import Reservation


class Command(BaseCommand):
    help = "Send a guest message via Channex → Booking.com for a reservation."

    def add_arguments(self, parser):
        parser.add_argument("--reservation-id", type=int, required=True)
        parser.add_argument(
            "--message-file",
            type=str,
            required=True,
            help="Path to message text file (body after first --- separator is used).",
        )
        parser.add_argument(
            "--tenant-slug",
            type=str,
            default="uzorita",
        )

    def handle(self, *args, **options):
        reservation = Reservation.objects.filter(pk=options["reservation_id"]).first()
        if reservation is None:
            raise CommandError(f"Reservation id={options['reservation_id']} not found.")

        path = Path(options["message_file"]).expanduser()
        if not path.is_file():
            raise CommandError(f"Message file not found: {path}")

        text = path.read_text(encoding="utf-8")
        message = text.split("---", 1)[-1].strip()
        if not message:
            raise CommandError("Message body is empty.")

        integration = get_active_channex_integration(options["tenant_slug"])
        try:
            row = send_message_for_reservation(integration, reservation, message)
        except ChannexBookingIngestError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Sent message for #{reservation.pk} {reservation.booking_code}: "
                f"{row.channex_message_id}"
            )
        )
