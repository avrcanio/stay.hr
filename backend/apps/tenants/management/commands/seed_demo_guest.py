from __future__ import annotations

import json
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.tenants.models import Tenant

DEFAULT_BOOKING_CODE = "MOCK-EVISITOR-001"
DEFAULT_UNIT_CODE = "STD-01"

# Canonical eVisitor-ready profile (see integrations/tests/test_smoke_evisitor.py).
GUEST_DEFAULTS = {
    "first_name": "Test",
    "last_name": "Guest",
    "name": "Test Guest",
    "sex": "M",
    "date_of_birth": date(1990, 1, 1),
    "nationality": "DE",
    "document_type": "national_id",
    "document_number": "L1234567",
    "document_country_iso2": "DE",
    "document_country_iso3": "DEU",
    "document_country": "DE",
    "address": "Berlin, Grad Berlin",
    "email": "test.guest@example.de",
    "is_primary": True,
}


class Command(BaseCommand):
    help = (
        "Seed one eVisitor-ready reservation + primary guest on the demo tenant. "
        "Idempotent on booking code (default MOCK-EVISITOR-001). Does not call HTZ API "
        "or modify evisitor_status on existing guests."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="demo")
        parser.add_argument("--property-slug", default="demo")
        parser.add_argument("--booking-code", default=DEFAULT_BOOKING_CODE)
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit a single JSON object on stdout.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if not tenant:
            raise CommandError(f"Tenant slug={options['tenant_slug']!r} not found.")

        prop = Property.objects.filter(tenant=tenant, slug=options["property_slug"]).first()
        if not prop:
            raise CommandError(
                f"Property slug={options['property_slug']!r} not found on tenant {tenant.slug!r}."
            )

        unit = Unit.objects.filter(
            tenant=tenant,
            property=prop,
            code=DEFAULT_UNIT_CODE,
        ).first()
        if not unit:
            raise CommandError(
                f"Unit code={DEFAULT_UNIT_CODE!r} not found on property {prop.slug!r}."
            )

        booking_code = options["booking_code"]
        today = timezone.localdate()
        check_out = today + timedelta(days=2)

        reservation, _created = Reservation.objects.update_or_create(
            tenant=tenant,
            booking_code=booking_code,
            defaults={
                "property": prop,
                "check_in": today,
                "check_out": check_out,
                "status": Reservation.Status.EXPECTED,
                "booker_name": GUEST_DEFAULTS["name"],
                "booker_email": GUEST_DEFAULTS["email"],
                "booker_phone": "+385911234567",
                "booker_country": "DE",
                "booker_address": GUEST_DEFAULTS["address"],
                "source": "Direct",
                "import_source": "",
                "units_count": 1,
                "persons_count": 1,
                "adults_count": 1,
                "nights_count": 2,
            },
        )

        ReservationUnit.objects.update_or_create(
            tenant=tenant,
            reservation=reservation,
            sort_order=0,
            defaults={
                "unit": unit,
                "room_name": unit.name,
            },
        )

        guest = Guest.objects.filter(reservation=reservation, is_primary=True).first()
        if guest is None:
            guest = Guest.objects.create(
                tenant=tenant,
                reservation=reservation,
                **GUEST_DEFAULTS,
            )
        else:
            for field, value in GUEST_DEFAULTS.items():
                setattr(guest, field, value)
            guest.save()

        Guest.objects.filter(reservation=reservation).exclude(pk=guest.pk).delete()

        payload = {
            "guest_id": guest.pk,
            "reservation_id": reservation.pk,
            "booking_code": booking_code,
        }

        if options["json"]:
            self.stdout.write(json.dumps(payload))
            return

        self.stdout.write(self.style.SUCCESS("Demo eVisitor guest ready."))
        self.stdout.write(f"guest_id={guest.pk}")
        self.stdout.write(f"reservation_id={reservation.pk}")
        self.stdout.write(f"booking_code={booking_code}")
