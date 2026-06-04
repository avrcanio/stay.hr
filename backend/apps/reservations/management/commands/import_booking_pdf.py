from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from apps.properties.models import Property
from apps.reservations.booking_pdf_import import parse_booking_pdf
from apps.reservations.booking_xls_import import upsert_reservation_from_xls_row
from apps.reservations.guest_slots import ensure_adult_guest_slots
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Import a Booking.com confirmation PDF into stay.hr (tenant-scoped)."

    def add_arguments(self, parser):
        parser.add_argument(
            "pdf_path",
            type=str,
            help="Path to Booking.com confirmation PDF.",
        )
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
            "--dry-run",
            action="store_true",
            help="Parse only; do not write to the database.",
        )
        parser.add_argument(
            "--fill-empty",
            action="store_true",
            help="For existing reservations: fill only empty fields.",
        )

    def handle(self, *args, **options):
        path = Path(options["pdf_path"]).expanduser()
        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        content = path.read_bytes()
        if not content.startswith(b"%PDF"):
            raise CommandError("File is not a valid PDF.")

        tenant = Tenant.objects.filter(pk=options["tenant_id"]).first()
        if tenant is None:
            raise CommandError(f"Tenant id={options['tenant_id']} not found.")

        prop = Property.objects.filter(tenant=tenant, slug=options["property_slug"]).first()
        if prop is None:
            raise CommandError(
                f"Property slug={options['property_slug']!r} not found on tenant {tenant.slug}."
            )

        try:
            row = parse_booking_pdf(content)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            f"Parsed {row.external_id} | {row.booker_name} | "
            f"{row.check_in_date} → {row.check_out_date} | "
            f"guests={row.guest_names} adults={row.adults_count}"
        )

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run: no changes written."))
            return

        existing_mode = "fill_empty" if options["fill_empty"] else "overwrite"
        result = upsert_reservation_from_xls_row(
            tenant=tenant,
            property=prop,
            row=row,
            existing_mode=existing_mode,
            authoritative_pdf=True,
        )

        if result.skipped:
            raise CommandError(
                f"Import skipped for {row.external_id}: {result.skip_reason or 'unknown'}"
            )

        reservation = Reservation.objects.get(pk=result.reservation_id)
        if reservation.confirmation_pdf:
            reservation.confirmation_pdf.delete(save=False)
        reservation.confirmation_pdf.save(
            f"{row.external_id}.pdf",
            ContentFile(content),
            save=True,
        )
        ensure_adult_guest_slots(
            tenant=tenant,
            reservation=reservation,
            adults_count=row.adults_count,
        )

        from apps.reservations.channel_availability_sync import (
            queue_reservation_channel_availability_sync,
        )

        queue_reservation_channel_availability_sync(reservation.pk)

        verb = "created" if result.created else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Import {verb}: reservation id={reservation.id} "
                f"booking={reservation.booking_code} "
                f"import_source={reservation.import_source} "
                f"(Channex ARI sync queued)"
            )
        )
