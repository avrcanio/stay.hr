from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.migrator import UzoritaLegacyMigrator, assert_legacy_db, legacy_db_configured


class Command(BaseCommand):
    help = "Idempotent import of Uzorita legacy data into Stay (tenant uzorita)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")
        parser.add_argument("--property-slug", default="uzorita")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run inside a transaction that rolls back at the end.",
        )
        parser.add_argument(
            "--skip-evisitor",
            action="store_true",
            help="Do not create/update eVisitor IntegrationConfig from UZORITA_EVISITOR_* env.",
        )

    def handle(self, *args, **options):
        if not legacy_db_configured():
            raise CommandError(
                "UZORITA_DB_* is not configured. Set UZORITA_DB_NAME, UZORITA_DB_USER, "
                "UZORITA_DB_PASSWORD, UZORITA_DB_HOST (and optional UZORITA_DB_PORT)."
            )

        try:
            assert_legacy_db()
        except Exception as exc:
            raise CommandError(f"Cannot connect to legacy database: {exc}") from exc

        migrator = UzoritaLegacyMigrator(
            tenant_slug=options["tenant_slug"],
            property_slug=options["property_slug"],
            dry_run=options["dry_run"],
            skip_evisitor=options["skip_evisitor"],
        )
        stats = migrator.run()

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Uzorita legacy migration finished."))
        self.stdout.write(f"  Properties created: {stats.properties}")
        self.stdout.write(f"  Units created: {stats.units}")
        self.stdout.write(f"  Reservations created: {stats.reservations}")
        self.stdout.write(f"  Reservation units created: {stats.reservation_units}")
        self.stdout.write(f"  Guests created: {stats.guests}")
        self.stdout.write(f"  eVisitor submissions created: {stats.evisitor_submissions}")
        self.stdout.write(f"  eVisitor configs created: {stats.integration_configs}")
        self.stdout.write(
            f"  Monthly statistics overrides created: {stats.monthly_statistics_overrides}"
        )

        if stats.errors:
            self.stdout.write(self.style.WARNING(f"  Warnings/errors: {len(stats.errors)}"))
            for msg in stats.errors[:20]:
                self.stdout.write(f"    - {msg}")
            if len(stats.errors) > 20:
                self.stdout.write(f"    ... and {len(stats.errors) - 20} more")

        tenant = options["tenant_slug"]
        self.stdout.write(
            f"\nNext: python manage.py validate_uzorita_migration --tenant-slug {tenant}"
        )
        self.stdout.write(
            "Then (once): python manage.py create_api_app "
            f'--tenant {tenant} --name "Hospira tablet 1" --profile reception'
        )
