from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand

from apps.properties.models import Unit
from apps.reservations.reservation_units import resync_unit_assignments
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Re-resolve reservation unit assignments from room_name (updates unit_id only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            type=int,
            default=2,
            help="Tenant primary key (default: 2).",
        )
        parser.add_argument(
            "--from-date",
            type=str,
            default="",
            help="Only reservations with check_in on/after YYYY-MM-DD.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print changes without updating unit_id.",
        )

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant id={tenant_id} not found."))
            return

        from_date = self._parse_from_date(options["from_date"])
        changes = resync_unit_assignments(
            tenant=tenant,
            from_date=from_date,
            dry_run=options["dry_run"],
        )

        if from_date:
            self.stdout.write(
                f"Tenant {tenant_id} ({tenant.name}), check_in >= {from_date}: "
                f"{len(changes)} unit assignment(s) to update."
            )
        else:
            self.stdout.write(
                f"Tenant {tenant_id} ({tenant.name}): "
                f"{len(changes)} unit assignment(s) to update."
            )

        for change in changes:
            row = change.reservation_unit
            reservation = row.reservation
            label = reservation.external_id or reservation.booking_code or reservation.pk
            old_code = "—"
            if change.old_unit_id:
                old_unit = Unit.objects.filter(pk=change.old_unit_id).first()
                old_code = old_unit.code if old_unit else str(change.old_unit_id)
            new_code = "—"
            if change.new_unit_id:
                new_unit = Unit.objects.filter(pk=change.new_unit_id).first()
                new_code = new_unit.code if new_unit else str(change.new_unit_id)

            self.stdout.write(
                f"  {label} #{row.sort_order} {row.room_name!r}: "
                f"{old_code} → {new_code}"
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no changes written."))
        elif changes:
            self.stdout.write(
                self.style.SUCCESS(f"Done. Updated {len(changes)} reservation unit row(s).")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Done. No changes needed."))

    @staticmethod
    def _parse_from_date(raw: str) -> date | None:
        if not raw:
            return None
        try:
            return date.fromisoformat(raw.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid --from-date {raw!r}; use YYYY-MM-DD.") from exc
