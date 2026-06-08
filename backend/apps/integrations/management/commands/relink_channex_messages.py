from django.core.management.base import BaseCommand, CommandError

from apps.integrations.channex.message_service import relink_unlinked_channex_messages
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Relink ChannexMessage rows that were stored without a reservation FK."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            raise CommandError(f"Tenant not found: {options['tenant_slug']}")

        updated = relink_unlinked_channex_messages(tenant)
        self.stdout.write(self.style.SUCCESS(f"Relinked {updated} Channex message(s)."))
