import os

from django.core.management.base import BaseCommand

from apps.integrations.channex.webhook_auth import generate_webhook_secret
from django.db import transaction

from apps.integrations.channex.booking_test import (
    BOOKING_COM_TEST_HOTEL_ID,
    BOOKING_COM_TEST_ROOMS,
    CHANNEX_BOOKING_TEST_CHANNEL_ID,
    CHANNEX_BOOKING_TEST_PROPERTY_SLUG,
)
from apps.integrations.channex.demo_property import CHANNEX_DEMO_PROPERTY_ID
from apps.integrations.channex.mapping import UZORITA_STAGING_ROOM_TYPES, room_types_config_payload
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property, Unit
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Create stay.hr property + units for Booking.com test hotel (10745030) "
        "and merge into Channex IntegrationConfig (uzorita tenant)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-slug",
            default="uzorita",
            help="Tenant that owns the test property (default: uzorita).",
        )
        parser.add_argument(
            "--also-demo",
            action="store_true",
            help="Also create the same property on demo tenant (admin tenant id=1).",
        )
        parser.add_argument(
            "--property-slug",
            default=CHANNEX_BOOKING_TEST_PROPERTY_SLUG,
        )

    @transaction.atomic
    def _seed_property(self, tenant: Tenant, property_slug: str) -> Property:
        prop, created = Property.objects.update_or_create(
            tenant=tenant,
            slug=property_slug,
            defaults={
                "name": "Booking.com test (Channex)",
                "timezone": "Europe/Zagreb",
                "language": "hr",
                "contact": {
                    "booking_hotel_id": BOOKING_COM_TEST_HOTEL_ID,
                    "channex_channel_id": CHANNEX_BOOKING_TEST_CHANNEL_ID,
                },
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(f"  {verb} property {prop.slug} (id={prop.id}) for tenant {tenant.slug}")

        for spec in BOOKING_COM_TEST_ROOMS:
            unit, u_created = Unit.objects.update_or_create(
                tenant=tenant,
                property=prop,
                code=spec["unit_code"],
                defaults={
                    "name": spec["name"],
                    "capacity_adults": spec["capacity_adults"],
                    "capacity_children": spec["capacity_children"],
                    "is_active": True,
                },
            )
            u_verb = "Created" if u_created else "Updated"
            self.stdout.write(
                f"    {u_verb} unit {unit.code} id={unit.id} "
                f"(booking_room_id={spec['booking_room_id']}, adults={spec['capacity_adults']})"
            )
        return prop

    def _merge_channex_config(self, tenant: Tenant, prop: Property) -> None:
        if tenant.slug != "uzorita":
            self.stdout.write(
                self.style.WARNING(
                    "Skipping IntegrationConfig merge (only uzorita has Channex config)."
                )
            )
            return

        booking_rooms = []
        for spec in BOOKING_COM_TEST_ROOMS:
            unit = Unit.objects.filter(
                tenant=tenant,
                property=prop,
                code=spec["unit_code"],
            ).first()
            row = {
                "unit_code": spec["unit_code"],
                "booking_room_id": spec["booking_room_id"],
                "booking_title": spec["booking_title"],
                "capacity_adults": spec["capacity_adults"],
                "channex_room_type_id": spec["channex_room_type_id"],
                "channex_title": spec["channex_title"],
                "rate_plans": list(spec.get("rate_plans") or []),
            }
            if unit:
                row["unit_id"] = unit.id
            booking_rooms.append(row)

        webhook_secret = os.getenv("CHANNEX_WEBHOOK_SECRET", "").strip()
        if not webhook_secret:
            webhook_secret = generate_webhook_secret()
            self.stdout.write(
                self.style.WARNING(
                    "CHANNEX_WEBHOOK_SECRET not set — generated new secret; "
                    "add it to .env and Channex webhook Headers."
                )
            )
            self.stdout.write(f"  CHANNEX_WEBHOOK_SECRET={webhook_secret}")

        config = {
            "environment": "staging",
            "base_url": "https://staging.channex.io/api/v1",
            "property_id": (
                os.getenv("CHANNEX_PROPERTY_ID", "").strip() or CHANNEX_DEMO_PROPERTY_ID
            ),
            "channex_property_title": "Test Property - Stay.hr",
            "api_key": os.getenv("CHANNEX_API_KEY", "").strip(),
            "webhook_secret": webhook_secret,
            "webhook_callback_url": "https://api.stay.hr/api/v1/integrations/channex/webhook/",
            "channel_id": CHANNEX_BOOKING_TEST_CHANNEL_ID,
            "booking_hotel_id": BOOKING_COM_TEST_HOTEL_ID,
            "certification_property_slug": prop.slug,
            "room_types": room_types_config_payload(),
            "booking_test_rooms": booking_rooms,
            "physical_room_types": list(UZORITA_STAGING_ROOM_TYPES),
        }

        row, created = IntegrationConfig.objects.update_or_create(
            tenant=tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            property=Property.objects.filter(tenant=tenant, slug="uzorita").first(),
            defaults={"is_active": True},
        )
        row.set_config_dict(config)
        row.save(update_fields=["config_encrypted", "config", "is_active", "updated_at"])
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"  {verb} Channex IntegrationConfig id={row.pk}"))

    def handle(self, *args, **options):
        slugs = [options["tenant_slug"]]
        if options["also_demo"]:
            slugs.append("demo")

        for slug in dict.fromkeys(slugs):
            tenant = Tenant.objects.filter(slug=slug).first()
            if tenant is None:
                self.stderr.write(self.style.ERROR(f"Tenant not found: {slug}"))
                continue
            self.stdout.write(self.style.MIGRATE_HEADING(f"Tenant: {tenant.slug} (id={tenant.id})"))
            prop = self._seed_property(tenant, options["property_slug"])
            self._merge_channex_config(tenant, prop)

        self.stdout.write("")
        self.stdout.write("Channex Mapping tab (Booking.com test):")
        for spec in BOOKING_COM_TEST_ROOMS:
            self.stdout.write(
                f"  {spec['booking_title']} ({spec['booking_room_id']}) → "
                f"{spec['channex_title']} ({spec['channex_room_type_id']})"
            )
        self.stdout.write("")
        self.stdout.write(
            "Admin: https://admin.stay.hr/admin/properties/property/ "
            f"(filter tenant {options['tenant_slug']}, slug {options['property_slug']})"
        )
        if options["tenant_slug"] == "uzorita":
            self.stdout.write("Tenant Uzorita: https://admin.stay.hr/admin/tenants/tenant/2/change/")
        self.stdout.write("Tenant Demo (id=1): https://admin.stay.hr/admin/tenants/tenant/1/change/")
