from django.core.management.base import BaseCommand, CommandError

from apps.integrations.channex.booking_service import process_channex_booking_revision
from apps.integrations.channex.demo_property import CHANNEX_CERT_TENANT_SLUG
from apps.integrations.models import IntegrationConfig


class Command(BaseCommand):
    help = "Fetch a Channex booking revision, ingest into stay.hr, and acknowledge."

    def add_arguments(self, parser):
        parser.add_argument("revision_id", help="Channex booking revision UUID")
        parser.add_argument("--tenant-slug", default=CHANNEX_CERT_TENANT_SLUG)

    def handle(self, *args, **options):
        tenant_slug = options["tenant_slug"]
        revision_id = options["revision_id"].strip()

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

        reservation = process_channex_booking_revision(row, revision_id)
        self.stdout.write(
            self.style.SUCCESS(
                f"Ingested reservation id={reservation.id} "
                f"external_id={reservation.external_id} "
                f"booking_code={reservation.booking_code} "
                f"status={reservation.status}"
            )
        )
