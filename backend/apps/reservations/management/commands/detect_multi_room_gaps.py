from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand

from apps.reservations.multi_room_guard import find_all_multi_room_gaps
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Detect multi-room inventory gaps (incomplete ReservationUnit mapping) "
        "and Channex calendar mismatches."
    )

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
            help="Only gaps for reservations with check_out after YYYY-MM-DD.",
        )

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant id={tenant_id} not found."))
            return

        from_date = self._parse_from_date(options["from_date"])
        gaps = find_all_multi_room_gaps(tenant=tenant, from_date=from_date)

        if not gaps:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Tenant {tenant_id} ({tenant.name}): no multi-room gaps."
                )
            )
            return

        self.stdout.write(
            f"Tenant {tenant_id} ({tenant.name}): {len(gaps)} multi-room gap(s)."
        )
        for gap in gaps:
            code = gap.get("booking_code") or gap["reservation_id"]
            name = (gap.get("booker_name") or "").strip()
            label = f"{code} {name}".strip()
            self.stdout.write(
                f"#{gap['reservation_id']}  {label}  "
                f"{gap['check_in']} .. {gap['check_out']}  "
                f"units_count={gap.get('units_count')}  "
                f"source={gap.get('import_source') or '-'}"
            )
            for issue in gap.get("issues") or []:
                self.stdout.write(f"  - {issue}")

        self.stderr.write(
            self.style.ERROR(f"Found {len(gaps)} multi-room gap(s).")
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
