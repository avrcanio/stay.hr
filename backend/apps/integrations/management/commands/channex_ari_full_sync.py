from django.core.management.base import BaseCommand

from apps.integrations.channex.ari_service import (
    build_full_sync,
    get_active_channex_integration,
    push_channex_ari,
    seed_channel_rate_plans_from_config,
)
from apps.integrations.channex.demo_property import CHANNEX_CERT_TENANT_SLUG


class Command(BaseCommand):
    help = "Build 500-day ARI in stay.hr and push full sync to Channex (cert test 1)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default=CHANNEX_CERT_TENANT_SLUG)
        parser.add_argument("--days", type=int, default=500)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Populate DB only, do not call Channex API.",
        )

    def handle(self, *args, **options):
        integration = get_active_channex_integration(options["tenant_slug"])
        seed_channel_rate_plans_from_config(integration)
        availability_values, restriction_values = build_full_sync(
            integration, days=options["days"]
        )
        self.stdout.write(
            f"Prepared availability batches={len(availability_values)} "
            f"restrictions batches={len(restriction_values)}"
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — skipping Channex push."))
            return

        results = push_channex_ari(integration)
        for row in results:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {row['kind']}: task_ids={row['task_ids']} values={row['values_count']}"
                )
            )
