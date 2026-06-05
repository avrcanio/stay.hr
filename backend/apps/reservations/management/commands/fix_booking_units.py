from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.properties.models import Property
from apps.reservations.channel_availability_sync import (
    queue_sync_if_units_changed,
    reservation_unit_codes,
)
from apps.reservations.channel_sync import IMPORT_SOURCE_BOOKING_PDF
from apps.reservations.models import Reservation
from apps.reservations.reservation_units import (
    apply_unit_amounts_from_total,
    sync_reservation_units,
)
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Sync ReservationUnit rows from comma-separated Booking.com room names "
        "and optionally lock with booking_pdf authority."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            type=int,
            default=2,
            help="Tenant primary key (default: 2 = uzorita).",
        )
        parser.add_argument(
            "--property-slug",
            type=str,
            default="uzorita",
            help="Property slug on tenant (default: uzorita).",
        )
        parser.add_argument(
            "--booking-code",
            type=str,
            required=True,
            help="Booking.com reservation number.",
        )
        parser.add_argument(
            "--room-names",
            type=str,
            required=True,
            help="Comma-separated room names (Booking.com unit titles).",
        )
        parser.add_argument(
            "--units-count",
            type=int,
            default=0,
            help="Optional units_count override (default: inferred from room names).",
        )
        parser.add_argument(
            "--pdf-lock",
            action="store_true",
            help="Set import_source=booking_pdf and pdf_imported_at (Channex won't replace units).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show planned changes without writing.",
        )

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(pk=options["tenant_id"]).first()
        if tenant is None:
            raise CommandError(f"Tenant id={options['tenant_id']} not found.")

        prop = Property.objects.filter(tenant=tenant, slug=options["property_slug"]).first()
        if prop is None:
            raise CommandError(
                f"Property slug={options['property_slug']!r} not found on tenant {tenant.slug}."
            )

        booking_code = options["booking_code"].strip()
        reservation = Reservation.objects.filter(
            tenant=tenant,
            booking_code=booking_code,
        ).first()
        if reservation is None:
            raise CommandError(f"Reservation booking_code={booking_code!r} not found.")

        room_names = options["room_names"].strip()
        units_count = options["units_count"] or len(
            [part for part in room_names.split(",") if part.strip()]
        )
        before_codes = reservation_unit_codes(reservation)

        self.stdout.write(
            f"#{reservation.pk} {reservation.booker_name} ({booking_code}) "
            f"units before={sorted(before_codes)}"
        )
        self.stdout.write(f"  room_names={room_names!r} units_count={units_count}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: no changes written."))
            return

        if options["pdf_lock"]:
            now = timezone.now()
            reservation.import_source = IMPORT_SOURCE_BOOKING_PDF
            reservation.pdf_imported_at = now
            reservation.units_count = units_count
            reservation.save(
                update_fields=[
                    "import_source",
                    "pdf_imported_at",
                    "units_count",
                    "updated_at",
                ]
            )
        elif reservation.units_count != units_count:
            reservation.units_count = units_count
            reservation.save(update_fields=["units_count", "updated_at"])

        units = sync_reservation_units(
            tenant=tenant,
            property=prop,
            reservation=reservation,
            room_name=room_names,
        )
        apply_unit_amounts_from_total(
            reservation=reservation,
            total_amount=reservation.amount,
            units=units,
        )

        after_codes = reservation_unit_codes(reservation)
        queued = queue_sync_if_units_changed(reservation, before_codes=before_codes)
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated #{reservation.pk}: units after={sorted(after_codes)} "
                f"channex_sync={'queued' if queued else 'unchanged'}"
            )
        )
