from django.core.management.base import BaseCommand
from django.core.management import call_command

from apps.integrations.channex.demo_property import CHANNEX_CERT_TENANT_SLUG
from apps.integrations.models import IntegrationConfig


class Command(BaseCommand):
    help = (
        "Move Channex certification setup to tenant demo (id=1): "
        "seed property, IntegrationConfig, rate plans; deactivate uzorita."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-rate-plans",
            action="store_true",
            help="Skip seed_channex_rate_plans after config seed.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Channex cert → tenant demo (id=1)"))

        call_command(
            "seed_channex_booking_test_property",
            tenant_slug=CHANNEX_CERT_TENANT_SLUG,
            deactivate_other_tenants=True,
        )

        if not options["skip_rate_plans"]:
            call_command("seed_channex_rate_plans", tenant_slug=CHANNEX_CERT_TENANT_SLUG)

        call_command("migrate_channex_cert_data_to_demo")

        active = IntegrationConfig.objects.filter(
            provider=IntegrationConfig.Provider.CHANNEX,
            is_active=True,
            tenant__slug=CHANNEX_CERT_TENANT_SLUG,
        ).first()
        if active:
            cfg = active.get_config_dict()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Active Channex config: tenant={CHANNEX_CERT_TENANT_SLUG} "
                    f"property={cfg.get('certification_property_slug')} "
                    f"config_id={active.pk}"
                )
            )
        else:
            self.stdout.write(self.style.ERROR("No active Channex config on demo tenant."))

        self.stdout.write("")
        self.stdout.write(
            "Optional: re-run cert ARI on demo with "
            "`python manage.py channex_ari_full_sync --tenant-slug demo`"
        )
