from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.channex.ari_service import get_active_channex_integration
from apps.integrations.channex.cancel_service import (
    cancel_booking_for_reservation,
    is_channex_cancel_eligible,
    mark_reservation_canceled_locally,
)
from apps.integrations.channex.exceptions import ChannexBookingIngestError
from apps.reservations.models import Reservation


class Command(BaseCommand):
    help = "Cancel a Channex/Booking.com reservation (CRS API) and optionally mark stay.hr canceled."

    def add_arguments(self, parser):
        parser.add_argument("--reservation-id", type=int, required=True)
        parser.add_argument(
            "--tenant-slug",
            type=str,
            default="uzorita",
        )
        parser.add_argument(
            "--mark-local-on-failure",
            action="store_true",
            help="Set stay.hr status=canceled even if Channex API fails.",
        )
        parser.add_argument(
            "--mark-local-only",
            action="store_true",
            help="Skip Channex API; only update stay.hr status.",
        )

    def handle(self, *args, **options):
        reservation = Reservation.objects.filter(pk=options["reservation_id"]).first()
        if reservation is None:
            raise CommandError(f"Reservation id={options['reservation_id']} not found.")

        if options["mark_local_only"]:
            mark_reservation_canceled_locally(
                reservation,
                note_suffix=" (stay.hr only — Channex/B.com ručno)",
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Marked canceled locally: #{reservation.pk} {reservation.booking_code}"
                )
            )
            return

        if not is_channex_cancel_eligible(reservation):
            raise CommandError(
                f"Reservation #{reservation.pk} is not eligible for Channex cancel."
            )

        integration = get_active_channex_integration(options["tenant_slug"])
        try:
            booking_id = cancel_booking_for_reservation(integration, reservation)
        except ChannexBookingIngestError as exc:
            if options["mark_local_on_failure"]:
                mark_reservation_canceled_locally(
                    reservation,
                    note_suffix=f" Channex cancel failed: {exc}",
                )
                self.stderr.write(
                    self.style.WARNING(
                        f"Channex cancel failed for #{reservation.pk}; marked locally: {exc}"
                    )
                )
                return
            raise CommandError(str(exc)) from exc

        mark_reservation_canceled_locally(
            reservation,
            note_suffix=f" Channex booking {booking_id} cancelled.",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Canceled #{reservation.pk} {reservation.booking_code} "
                f"(Channex {booking_id})"
            )
        )
