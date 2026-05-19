from django.core.management.base import BaseCommand

from apps.integrations.channex.ari_service import (
    flush_channex_ari_outbox,
    get_active_channex_integration,
)


class Command(BaseCommand):
    help = "Flush pending Channex ARI outbox entries."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")

    def handle(self, *args, **options):
        integration = get_active_channex_integration(options["tenant_slug"])
        results = flush_channex_ari_outbox(integration)
        if not results:
            self.stdout.write("No pending outbox entries.")
            return
        for row in results:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{row['kind']}: task_ids={row['task_ids']} values={row['values_count']}"
                )
            )
