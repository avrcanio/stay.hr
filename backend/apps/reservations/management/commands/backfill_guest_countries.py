"""Backfill guest nationality from reservation booker/primary guest when missing."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.reservations.models import Guest
from apps.reservations.nationality_display import (
    apply_reservation_country_to_guest_if_empty,
    guest_nationality_iso2,
)


class Command(BaseCommand):
    help = (
        "Set guest nationality/document_country_iso2 from reservation when empty "
        "(booker_country or another guest on the same reservation)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int)
        parser.add_argument("--reservation-id", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        qs = Guest.objects.select_related("reservation").order_by("pk")
        if options.get("tenant_id"):
            qs = qs.filter(tenant_id=options["tenant_id"])
        if options.get("reservation_id"):
            qs = qs.filter(reservation_id=options["reservation_id"])

        updated = 0
        for guest in qs.iterator():
            if guest_nationality_iso2(guest):
                continue
            fields = apply_reservation_country_to_guest_if_empty(guest)
            if not fields:
                continue
            if options.get("dry_run"):
                self.stdout.write(
                    f"guest {guest.pk} ({guest.name}): would set {fields} "
                    f"from reservation {guest.reservation_id}"
                )
            else:
                guest.save(update_fields=[*fields, "updated_at"])
                self.stdout.write(
                    f"guest {guest.pk} ({guest.name}): updated {fields} "
                    f"from reservation {guest.reservation_id}"
                )
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Updated {updated} guest(s)."))
