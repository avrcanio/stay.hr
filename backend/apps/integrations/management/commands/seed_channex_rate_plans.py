from django.core.management.base import BaseCommand

from apps.integrations.channex.ari_service import (
    get_active_channex_integration,
    seed_channel_rate_plans_from_config,
)


class Command(BaseCommand):
    help = "Seed ChannelRatePlan rows from Channex IntegrationConfig booking_test_rooms."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")

    def handle(self, *args, **options):
        integration = get_active_channex_integration(options["tenant_slug"])
        created = seed_channel_rate_plans_from_config(integration)
        self.stdout.write(self.style.SUCCESS(f"Seeded channel rate plans (new={created})"))
