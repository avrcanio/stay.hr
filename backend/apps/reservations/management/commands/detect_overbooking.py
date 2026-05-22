from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand

from apps.reservations.overbooking import find_conflicts
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Detect overlapping reservations assigned to the same unit."

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
            help="Only conflicts with overlap ending after YYYY-MM-DD.",
        )

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant id={tenant_id} not found."))
            return

        from_date = self._parse_from_date(options["from_date"])
        conflicts = find_conflicts(tenant=tenant, from_date=from_date)

        if not conflicts:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Tenant {tenant_id} ({tenant.name}): no overbooking conflicts."
                )
            )
            return

        self.stdout.write(
            f"Tenant {tenant_id} ({tenant.name}): {len(conflicts)} conflict(s)."
        )
        for conflict in conflicts:
            self.stdout.write(
                f"{conflict.unit.code}  overlap {conflict.overlap_from} .. {conflict.overlap_to}"
            )
            self.stdout.write(
                f"  OSTAJE:     {_reservation_label(conflict.incumbent)} "
                f"(check-in {conflict.incumbent.check_in})"
            )
            self.stdout.write(
                f"  AKCIJA:     {_reservation_label(conflict.conflicting)} "
                f"(check-in {conflict.conflicting.check_in})"
            )

        self.stderr.write(
            self.style.ERROR(f"Found {len(conflicts)} overbooking conflict(s).")
        )
        raise SystemExit(1)

    @staticmethod
    def _parse_from_date(raw: str) -> date | None:
        if not raw:
            return None
        try:
            return date.fromisoformat(raw.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid --from-date {raw!r}; use YYYY-MM-DD.") from exc


def _reservation_label(reservation) -> str:
    code = reservation.external_id or reservation.booking_code or str(reservation.pk)
    return f"{code} {reservation.booker_name}".strip()
