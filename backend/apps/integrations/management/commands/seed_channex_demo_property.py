from django.core.management.base import BaseCommand
from django.db import transaction

from apps.integrations.channex.booking_test import BOOKING_COM_TEST_ROOMS
from apps.integrations.channex.demo_property import (
    CHANNEX_DEMO_CONTACT,
    CHANNEX_DEMO_CURRENCY,
    CHANNEX_DEMO_PROPERTY_SLUG,
    CHANNEX_DEMO_PROPERTY_TITLE,
    UZORITA_LOCATION,
)
from apps.properties.models import Property, Unit
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Create Channex certification demo property on stay.hr (tenant demo, id=1)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="demo")

    @transaction.atomic
    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant not found: {options['tenant_slug']}"))
            return

        prop, created = Property.objects.update_or_create(
            tenant=tenant,
            slug=CHANNEX_DEMO_PROPERTY_SLUG,
            defaults={
                "name": CHANNEX_DEMO_PROPERTY_TITLE,
                "address": (
                    f"{UZORITA_LOCATION['address']}, {UZORITA_LOCATION['postal_code']} "
                    f"{UZORITA_LOCATION['city']}, {UZORITA_LOCATION['country_name']}"
                ),
                "timezone": UZORITA_LOCATION["timezone"],
                "language": "hr",
                "contact": {
                    **CHANNEX_DEMO_CONTACT,
                    **UZORITA_LOCATION,
                    "currency": CHANNEX_DEMO_CURRENCY,
                    "property_type": "hotel",
                },
                "branding": {
                    "channex": True,
                    "certification": True,
                },
            },
        )

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} property '{prop.name}' slug={prop.slug} id={prop.id} "
                f"(tenant {tenant.slug} id={tenant.id})"
            )
        )

        for spec in BOOKING_COM_TEST_ROOMS:
            unit, u_created = Unit.objects.update_or_create(
                tenant=tenant,
                property=prop,
                code=spec["unit_code"],
                defaults={
                    "name": spec["booking_title"],
                    "capacity_max_guests": spec["capacity_max_guests"],
                    "capacity_adults": spec["capacity_adults"],
                    "capacity_children": spec["capacity_children"],
                    "capacity_infants": spec["capacity_infants"],
                    "is_active": True,
                },
            )
            u_verb = "Created" if u_created else "Updated"
            self.stdout.write(
                f"  {u_verb} {unit.code} id={unit.id} — {spec['booking_title']} "
                f"(Booking {spec['booking_room_id']}, "
                f"guests={spec['capacity_max_guests']}, adults={spec['capacity_adults']})"
            )

        self.stdout.write("")
        self.stdout.write("Admin:")
        self.stdout.write(f"  Tenant: https://admin.stay.hr/admin/tenants/tenant/{tenant.id}/change/")
        self.stdout.write(f"  Property: https://admin.stay.hr/admin/properties/property/{prop.id}/change/")
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Channex Create Property form (staging) — copy values:"))
        self.stdout.write(f"  Title:             {CHANNEX_DEMO_PROPERTY_TITLE}")
        self.stdout.write(f"  Default Currency:  {CHANNEX_DEMO_CURRENCY}")
        self.stdout.write("  Property Type:     Hotel (or Apartment)")
        self.stdout.write(f"  Email:             {CHANNEX_DEMO_CONTACT['email']}")
        self.stdout.write(f"  Phone:             {CHANNEX_DEMO_CONTACT['phone']}")
        self.stdout.write(f"  Website:           {CHANNEX_DEMO_CONTACT['website']}")
        self.stdout.write(f"  Country:           {UZORITA_LOCATION['country_name']}")
        self.stdout.write(f"  Timezone:          {UZORITA_LOCATION['timezone']}")
        self.stdout.write(f"  Postal Code:       {UZORITA_LOCATION['postal_code']}")
        self.stdout.write(f"  City:              {UZORITA_LOCATION['city']}")
        self.stdout.write(f"  Address:           {UZORITA_LOCATION['address']}")
        self.stdout.write(
            f"  Latitude/Longitude: {UZORITA_LOCATION['latitude']}, {UZORITA_LOCATION['longitude']}"
        )
