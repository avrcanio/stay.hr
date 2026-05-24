import os

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.config_secrets import credentials_status_summary
from apps.integrations.models import IntegrationConfig
from apps.tenants.models import Tenant

CHANNEX_DEFAULT_BASE_URL = "https://staging.channex.io/api/v1"


class Command(BaseCommand):
    help = (
        "Merge CHANNEX_API_KEY, CHANNEX_WEBHOOK_SECRET, and CHANNEX_PROPERTY_ID from env "
        "into an existing Channex IntegrationConfig without changing room/mapping fields."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="demo")
        parser.add_argument(
            "--pk",
            type=int,
            default=None,
            help="IntegrationConfig primary key (optional; otherwise first active Channex row).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be merged without saving.",
        )

    def handle(self, *args, **options):
        api_key = os.getenv("CHANNEX_API_KEY", "").strip()
        webhook_secret = os.getenv("CHANNEX_WEBHOOK_SECRET", "").strip()
        property_id = os.getenv("CHANNEX_PROPERTY_ID", "").strip()

        if not any((api_key, webhook_secret, property_id)):
            raise CommandError(
                "Set at least one of CHANNEX_API_KEY, CHANNEX_WEBHOOK_SECRET, CHANNEX_PROPERTY_ID."
            )

        row = self._resolve_row(options)
        config = row.get_config_dict()
        room_types_before = config.get("room_types")
        booking_test_rooms_before = config.get("booking_test_rooms")

        updates: list[str] = []
        if api_key:
            config["api_key"] = api_key
            updates.append("api_key")
        if webhook_secret:
            config["webhook_secret"] = webhook_secret
            updates.append("webhook_secret")
        if property_id:
            config["property_id"] = property_id
            updates.append("property_id")

        if not config.get("environment"):
            config["environment"] = "staging"
            updates.append("environment (default)")
        if not config.get("base_url"):
            config["base_url"] = CHANNEX_DEFAULT_BASE_URL
            updates.append("base_url (default)")

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            f"{prefix}Channex IntegrationConfig id={row.pk} tenant={row.tenant.slug}: "
            f"merge {', '.join(updates)}"
        )

        if options["dry_run"]:
            self.stdout.write(credentials_status_summary(row.provider, config))
            return

        row.set_config_dict(config)
        row.save(update_fields=["config_encrypted", "config", "updated_at"])

        saved = row.get_config_dict()
        self.assert_mapping_unchanged(
            saved,
            room_types_before,
            booking_test_rooms_before,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated Channex IntegrationConfig id={row.pk} "
                f"({credentials_status_summary(row.provider, saved)})."
            )
        )

    def _resolve_row(self, options) -> IntegrationConfig:
        if options["pk"]:
            row = (
                IntegrationConfig.objects.filter(
                    pk=options["pk"],
                    provider=IntegrationConfig.Provider.CHANNEX,
                )
                .select_related("tenant")
                .first()
            )
            if row is None:
                raise CommandError(
                    f"No Channex IntegrationConfig with pk={options['pk']}."
                )
            return row

        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            raise CommandError(f"Tenant not found: {options['tenant_slug']}")

        row = (
            IntegrationConfig.objects.filter(
                tenant=tenant,
                provider=IntegrationConfig.Provider.CHANNEX,
                is_active=True,
            )
            .select_related("tenant")
            .order_by("-pk")
            .first()
        )
        if row is None:
            raise CommandError(
                f"No active Channex IntegrationConfig for tenant {tenant.slug}. "
                "Run seed_channex_booking_test_property first."
            )
        return row

    def assert_mapping_unchanged(
        self,
        saved: dict,
        room_types_before,
        booking_test_rooms_before,
    ) -> None:
        if room_types_before is not None and saved.get("room_types") != room_types_before:
            raise CommandError("room_types mapping changed unexpectedly.")
        if (
            booking_test_rooms_before is not None
            and saved.get("booking_test_rooms") != booking_test_rooms_before
        ):
            raise CommandError("booking_test_rooms mapping changed unexpectedly.")
