from django.core.management.base import BaseCommand, CommandError

from apps.integrations.channex.booking_service import backfill_channex_financial_fields
from apps.integrations.models import IntegrationConfig

DEFAULT_TENANT_SLUG = "uzorita"


class Command(BaseCommand):
    help = (
        "Backfill commission and payment fields on Channex reservations by fetching "
        "GET /bookings/:id or GET /bookings?filter[ota_reservation_code]=… from Channex."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-slug",
            default=DEFAULT_TENANT_SLUG,
            help=f"Tenant slug (default: {DEFAULT_TENANT_SLUG}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch from Channex and report changes without saving.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="include_with_commission",
            help="Include reservations that already have commission_amount (default: only missing).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most N reservations (for testing).",
        )

    def handle(self, *args, **options):
        tenant_slug = options["tenant_slug"]
        row = (
            IntegrationConfig.objects.filter(
                tenant__slug=tenant_slug,
                provider=IntegrationConfig.Provider.CHANNEX,
                is_active=True,
            )
            .select_related("tenant")
            .first()
        )
        if row is None:
            raise CommandError(f"No active Channex IntegrationConfig for tenant {tenant_slug}")

        only_missing = not options["include_with_commission"]
        dry_run = options["dry_run"]
        stats = backfill_channex_financial_fields(
            row,
            only_missing_commission=only_missing,
            dry_run=dry_run,
            limit=options["limit"],
        )

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(
            f"[{mode}] tenant={tenant_slug} processed={stats['processed']} "
            f"updated={stats['updated']} skipped_no_lookup={stats['skipped_no_lookup_code']} "
            f"skipped_no_data={stats['skipped_no_financial_data']} "
            f"not_found={stats['not_found']} errors={stats['errors']}"
        )

        updates = stats.get("updates") or []
        for entry in updates:
            commission = entry.get("commission_amount")
            provider = entry.get("payment_provider", "")
            lookup = entry.get("lookup_method", "")
            self.stdout.write(
                f"  reservation #{entry['reservation_id']} "
                f"booking_code={entry.get('booking_code') or '—'} "
                f"via={lookup} "
                f"commission={commission} provider={provider or '—'}"
            )

        if dry_run and updates:
            self.stdout.write(self.style.WARNING("Re-run without --dry-run to save changes."))
