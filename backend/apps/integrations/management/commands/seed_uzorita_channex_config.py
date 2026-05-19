import os

from django.core.management.base import BaseCommand

from apps.integrations.channex.demo_property import CHANNEX_DEMO_PROPERTY_ID
from apps.integrations.channex.mapping import room_types_config_payload
from apps.integrations.models import IntegrationConfig
from apps.properties.models import Property
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Create or update Channex IntegrationConfig for tenant uzorita (staging room type UUIDs)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")
        parser.add_argument("--property-slug", default="uzorita")
        parser.add_argument(
            "--property-id",
            default="",
            help="Channex property UUID (or set CHANNEX_PROPERTY_ID env).",
        )
        parser.add_argument(
            "--api-key",
            default="",
            help="Channex API key (or set CHANNEX_API_KEY env).",
        )
        parser.add_argument(
            "--environment",
            default="staging",
            choices=["staging", "production"],
        )

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant not found: {options['tenant_slug']}"))
            return

        prop = Property.objects.filter(tenant=tenant, slug=options["property_slug"]).first()
        property_id = (
            options["property_id"]
            or os.getenv("CHANNEX_PROPERTY_ID", "")
            or CHANNEX_DEMO_PROPERTY_ID
        ).strip()
        api_key = (options["api_key"] or os.getenv("CHANNEX_API_KEY", "")).strip()

        base_url = (
            "https://staging.channex.io/api/v1"
            if options["environment"] == "staging"
            else "https://app.channex.io/api/v1"
        )

        config = {
            "environment": options["environment"],
            "base_url": base_url,
            "property_id": property_id,
            "api_key": api_key,
            "room_types": room_types_config_payload(),
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
        self.stdout.write(self.style.SUCCESS(f"{verb} Channex IntegrationConfig id={row.pk}"))

        if not property_id:
            self.stdout.write(
                self.style.WARNING(
                    "property_id is empty — set CHANNEX_PROPERTY_ID or run with --property-id "
                    "(Channex → Properties → copy UUID)."
                )
            )
        if not api_key:
            self.stdout.write(
                self.style.WARNING(
                    "api_key is empty — set CHANNEX_API_KEY or run with --api-key "
                    "(Channex → API keys)."
                )
            )

        self.stdout.write("Room type mapping:")
        for rt in config["room_types"]:
            self.stdout.write(
                f"  {rt['unit_code']:3s} unit_id={rt.get('unit_id', '-'):>3} "
                f"→ {rt['channex_title']} ({rt['channex_room_type_id']})"
            )
