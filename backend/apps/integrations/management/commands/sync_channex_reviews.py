from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.channex.ari_service import get_active_channex_integration
from apps.integrations.channex.exceptions import ChannexApiError, ChannexBookingIngestError
from apps.integrations.channex.review_service import (
    repair_channex_review_replies,
    sync_reviews_from_channex,
)


class Command(BaseCommand):
    help = "Pull guest reviews from Channex for a tenant property."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", type=str, default="uzorita")
        parser.add_argument(
            "--max-pages",
            type=int,
            default=10,
            help="Maximum number of Channex API pages to fetch.",
        )

    def handle(self, *args, **options):
        tenant_slug = options["tenant_slug"]
        max_pages = options["max_pages"]

        try:
            integration = get_active_channex_integration(tenant_slug)
        except ChannexBookingIngestError as exc:
            raise CommandError(str(exc)) from exc

        try:
            rows = sync_reviews_from_channex(integration, max_pages=max_pages)
        except (ChannexBookingIngestError, ChannexApiError) as exc:
            raise CommandError(str(exc)) from exc

        repaired = repair_channex_review_replies(integration.tenant)
        self.stdout.write(self.style.SUCCESS(f"Synced {len(rows)} review row(s)."))
        if repaired:
            self.stdout.write(self.style.SUCCESS(f"Repaired {repaired} review reply row(s)."))
