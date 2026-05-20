from django.core.management.base import BaseCommand, CommandError

from apps.integrations.channex.booking_service import process_channex_booking_revisions_feed
from apps.integrations.channex.demo_property import CHANNEX_CERT_TENANT_SLUG
from apps.integrations.models import IntegrationConfig


class Command(BaseCommand):
    help = (
        "Process non-acknowledged Channex booking revisions from GET /booking_revisions/feed "
        "(fallback for missed webhooks)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-slug",
            default=CHANNEX_CERT_TENANT_SLUG,
            help=f"Tenant slug (default: {CHANNEX_CERT_TENANT_SLUG}).",
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

        reservations = process_channex_booking_revisions_feed(row)
        if not reservations:
            self.stdout.write(self.style.WARNING("No new revisions to process."))
            return

        for reservation in reservations:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Ingested reservation id={reservation.id} "
                    f"external_id={reservation.external_id} status={reservation.status}"
                )
            )
