from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.legacy_import.id_document_importer import UzoritaIdDocumentImporter
from apps.legacy_import.migrator import assert_legacy_db, legacy_db_configured


class Command(BaseCommand):
    help = (
        "Copy Uzorita id_documents media into Stay MEDIA_ROOT and import IdDocument rows "
        "linked to migrated guests (by legacy_id)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", default="uzorita")
        parser.add_argument(
            "--media-source",
            default="/opt/stacks/uzorita/rooms/code/backend/app/media",
            help="Uzorita MEDIA_ROOT on the host (mount read-only for docker run).",
        )
        parser.add_argument(
            "--skip-copy",
            action="store_true",
            help="Only import DB rows; assume files are already under Stay MEDIA_ROOT.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Roll back DB changes at the end.",
        )

    def handle(self, *args, **options):
        if not legacy_db_configured():
            raise CommandError("UZORITA_DB_* is not configured.")

        try:
            assert_legacy_db()
        except Exception as exc:
            raise CommandError(f"Cannot connect to legacy database: {exc}") from exc

        media_source = Path(options["media_source"])
        if not options["skip_copy"] and not media_source.is_dir():
            raise CommandError(
                f"Media source not found: {media_source}. "
                "Rsync manually or mount uzorita media when running via docker."
            )

        importer = UzoritaIdDocumentImporter(
            tenant_slug=options["tenant_slug"],
            media_source=None if options["skip_copy"] else media_source,
            skip_copy=options["skip_copy"],
            dry_run=options["dry_run"],
        )
        stats = importer.run()

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Uzorita ID document import finished."))
        self.stdout.write(f"  Files copied: {stats.files_copied}")
        self.stdout.write(f"  IdDocuments created: {stats.documents_created}")
        self.stdout.write(f"  Skipped: {stats.documents_skipped}")
        if stats.errors:
            self.stdout.write(self.style.WARNING(f"  Errors: {len(stats.errors)}"))
            for msg in stats.errors[:15]:
                self.stdout.write(f"    - {msg}")

        self.stdout.write(f"\nMEDIA_ROOT: {settings.MEDIA_ROOT}")
