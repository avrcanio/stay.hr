from django.core.management.base import BaseCommand, CommandError

from apps.integrations.models import IntegrationConfig
from apps.integrations.smoobu.booking_service import (
    default_modified_from,
    sync_smoobu_reservations,
)
from apps.integrations.smoobu.exceptions import SmoobuBookingIngestError
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Sync Smoobu reservations into stay.hr (tenant-scoped, production uzorita)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, default=2)
        parser.add_argument("--tenant-slug", default="")
        parser.add_argument(
            "--modified-from",
            default="",
            help="ISO date/datetime filter (default: config last_sync_modified_from or 30 days).",
        )
        parser.add_argument("--apartment-id", type=int, default=None)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and count bookings without writing to the database.",
        )

    def handle(self, *args, **options):
        tenant = self._resolve_tenant(options)
        row = (
            IntegrationConfig.objects.filter(
                tenant=tenant,
                provider=IntegrationConfig.Provider.SMOOBU,
                is_active=True,
            )
            .select_related("tenant", "property")
            .first()
        )
        if row is None:
            raise CommandError(
                f"No active Smoobu IntegrationConfig for tenant {tenant.slug} (id={tenant.pk})."
            )

        modified_from = (options["modified_from"] or "").strip() or None
        if modified_from is None:
            modified_from = default_modified_from(row)
            self.stdout.write(f"Using modified_from={modified_from}")

        try:
            stats = sync_smoobu_reservations(
                row,
                modified_from=modified_from,
                apartment_id=options["apartment_id"],
                dry_run=options["dry_run"],
            )
        except SmoobuBookingIngestError as exc:
            raise CommandError(str(exc)) from exc

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Smoobu sync for {tenant.slug}: "
                f"created={stats['created']} updated={stats['updated']} "
                f"skipped={stats['skipped']} errors={len(stats['errors'])}"
            )
        )
        if stats.get("last_sync_modified_from"):
            self.stdout.write(f"  last_sync_modified_from={stats['last_sync_modified_from']}")

        for err in stats.get("errors") or []:
            self.stderr.write(f"  {err.get('external_id')}: {err.get('error')}")

    def _resolve_tenant(self, options) -> Tenant:
        if options["tenant_slug"]:
            tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
            if tenant is None:
                raise CommandError(f"Tenant not found: {options['tenant_slug']}")
            return tenant

        tenant = Tenant.objects.filter(pk=options["tenant_id"]).first()
        if tenant is None:
            raise CommandError(f"Tenant not found: id={options['tenant_id']}")
        return tenant
