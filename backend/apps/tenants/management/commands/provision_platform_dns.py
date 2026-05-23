from django.core.management.base import BaseCommand, CommandError

from apps.tenants.cloudflare.client import CloudflareAPIError
from apps.tenants.cloudflare.dns import provision_platform_dns


class Command(BaseCommand):
    help = "Upsert proxied A records for app.stay.hr and *.stay.hr in Cloudflare."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print records that would be created without calling Cloudflare.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        try:
            records = provision_platform_dns(dry_run=dry_run)
        except CloudflareAPIError as exc:
            raise CommandError(str(exc)) from exc

        for line in records:
            prefix = "Would provision" if dry_run else "Provisioned"
            self.stdout.write(f"{prefix}: {line}")

        self.stdout.write(self.style.SUCCESS("Platform DNS provisioning complete."))
