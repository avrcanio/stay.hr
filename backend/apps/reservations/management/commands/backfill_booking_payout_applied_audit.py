from django.core.management.base import BaseCommand

from apps.reservations.booking_payout_models import (
    BookingPayoutImport,
    BookingPayoutImportStatus,
)


class Command(BaseCommand):
    help = (
        "Backfill BookingPayoutImport.applied_at/applied_by for fully synced APPLIED batches."
    )

    def handle(self, *args, **options):
        updated = 0
        queryset = BookingPayoutImport.objects.filter(
            status=BookingPayoutImportStatus.APPLIED,
            applied_at__isnull=True,
        )
        for import_batch in queryset.iterator():
            if import_batch.ensure_applied_audit():
                updated += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {import_batch.payout_id}: applied_at={import_batch.applied_at}"
                    )
                )
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} import(s)."))
