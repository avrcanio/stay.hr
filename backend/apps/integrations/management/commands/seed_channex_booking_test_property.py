import os

from django.core.management.base import BaseCommand

from apps.integrations.channex.webhook_auth import generate_webhook_secret
from django.db import transaction

from apps.integrations.channex.booking_test import (
    BOOKING_COM_TEST_HOTEL_ID,
    BOOKING_COM_TEST_ROOMS,
    CHANNEX_BOOKING_TEST_CHANNEL_ID,
    booking_test_room_types_config_payload,
    certification_property_slug,
)
from apps.integrations.channex.demo_property import (
    CHANNEX_CERT_TENANT_SLUG,
    CHANNEX_DEMO_PROPERTY_ID,
    CHANNEX_DEMO_PROPERTY_TITLE,
)
from apps.integrations.channex.mapping import UZORITA_STAGING_ROOM_TYPES
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property, Unit
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Create stay.hr Channex certification property + units and IntegrationConfig. "
        f"Default tenant: {CHANNEX_CERT_TENANT_SLUG} (id=1)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-slug",
            default=CHANNEX_CERT_TENANT_SLUG,
            help=f"Tenant for certification (default: {CHANNEX_CERT_TENANT_SLUG}).",
        )
        parser.add_argument(
            "--property-slug",
            default="",
            help="Property slug (default: channex-demo on demo tenant).",
        )
        parser.add_argument(
            "--deactivate-other-tenants",
            action="store_true",
            help="Deactivate Channex IntegrationConfig on other tenants.",
        )

    @transaction.atomic
    def _seed_property(self, tenant: Tenant, property_slug: str) -> Property:
        name = (
            CHANNEX_DEMO_PROPERTY_TITLE
            if property_slug == certification_property_slug(tenant.slug)
            else "Booking.com test (Channex)"
        )
        prop, created = Property.objects.update_or_create(
            tenant=tenant,
            slug=property_slug,
            defaults={
                "name": name,
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

        physical_rooms = (
            list(UZORITA_STAGING_ROOM_TYPES)
            if tenant.slug == "uzorita"
            else []
        )

        config = {
            "environment": "staging",
            "base_url": "https://staging.channex.io/api/v1",
            "property_id": (
                os.getenv("CHANNEX_PROPERTY_ID", "").strip() or CHANNEX_DEMO_PROPERTY_ID
            ),
            "channex_property_title": CHANNEX_DEMO_PROPERTY_TITLE,
            "api_key": os.getenv("CHANNEX_API_KEY", "").strip(),
            "webhook_secret": webhook_secret,
            "webhook_callback_url": "https://api.stay.hr/api/v1/integrations/channex/webhook/",
            "channel_id": CHANNEX_BOOKING_TEST_CHANNEL_ID,
            "booking_hotel_id": BOOKING_COM_TEST_HOTEL_ID,
            "certification_property_slug": prop.slug,
            "room_types": booking_test_room_types_config_payload(tenant.slug, prop.slug),
            "booking_test_rooms": booking_rooms,
            "physical_room_types": physical_rooms,
        }

        row, created = IntegrationConfig.objects.update_or_create(
            tenant=tenant,
            provider=IntegrationConfig.Provider.CHANNEX,
            property=prop,
            defaults={"is_active": True},
        )
        row.set_config_dict(config)
        row.save(update_fields=["config_encrypted", "config", "is_active", "updated_at"])
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"  {verb} Channex IntegrationConfig id={row.pk}"))

    def handle(self, *args, **options):
        tenant_slug = options["tenant_slug"]
        property_slug = options["property_slug"] or certification_property_slug(tenant_slug)

        tenant = Tenant.objects.filter(slug=tenant_slug).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant not found: {tenant_slug}"))
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"Tenant: {tenant.slug} (id={tenant.id})")
        )
        prop = self._seed_property(tenant, property_slug)
        self._merge_channex_config(tenant, prop)

        if options["deactivate_other_tenants"]:
            deactivated = (
                IntegrationConfig.objects.filter(
                    provider=IntegrationConfig.Provider.CHANNEX,
                    is_active=True,
                )
                .exclude(tenant=tenant)
                .update(is_active=False)
            )
            self.stdout.write(
                self.style.WARNING(f"Deactivated Channex config on other tenants: {deactivated}")
            )

        self.stdout.write("")
        self.stdout.write("Channex Mapping tab (Booking.com test):")
        for spec in BOOKING_COM_TEST_ROOMS:
            self.stdout.write(
                f"  {spec['booking_title']} ({spec['booking_room_id']}) → "
                f"{spec['channex_title']} ({spec['channex_room_type_id']})"
            )
        self.stdout.write("")
        self.stdout.write(
            f"Admin property: https://admin.stay.hr/admin/properties/property/{prop.id}/change/"
        )
        self.stdout.write(
            f"Admin tenant: https://admin.stay.hr/admin/tenants/tenant/{tenant.id}/change/"
        )
