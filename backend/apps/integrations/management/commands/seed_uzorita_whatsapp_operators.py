from django.core.management.base import BaseCommand

from apps.tenants.models import Tenant, TenantReceptionSettings

UZORITA_OPERATOR_PHONES = [
    {"name": "Toni Šupe", "phone": "+385998388513"},
    {"name": "Ante Vrcan", "phone": "+385976713511"},
]


class Command(BaseCommand):
    help = "Seed WhatsApp operator whitelist for Uzorita (tenant id=2 by default)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            type=int,
            default=2,
            help="Tenant primary key (default: 2 = Uzorita).",
        )

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant not found: id={tenant_id}"))
            return

        settings, created = TenantReceptionSettings.objects.get_or_create(tenant=tenant)
        settings.whatsapp_operator_phones = UZORITA_OPERATOR_PHONES
        settings.save(update_fields=["whatsapp_operator_phones", "updated_at"])

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} whatsapp_operator_phones for tenant id={tenant.pk} ({tenant.slug}): "
                f"{len(UZORITA_OPERATOR_PHONES)} operators."
            )
        )
