from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from apps.reservations.guest_slots import ensure_adult_guest_slots
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Add placeholder guests (Novi gost) on reservations where "
        "guests.count() < adults_count."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-date",
            type=str,
            default="",
            help="Only reservations with check_in on/after YYYY-MM-DD (default: today).",
        )
        parser.add_argument(
            "--tenant-id",
            type=int,
            default=0,
            help="Limit to tenant primary key (default: all tenants).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print matching reservations without creating guests.",
        )

    def handle(self, *args, **options):
        from_date = self._parse_from_date(options["from_date"])
        tenant_id = options["tenant_id"]

        qs = (
            Reservation.objects.filter(check_in__gte=from_date)
            .exclude(status=Reservation.Status.CANCELED)
            .annotate(guests_count=Count("guests"))
            .filter(adults_count__gt=0)
            .select_related("tenant")
            .order_by("check_in", "id")
        )
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
            if not Tenant.objects.filter(pk=tenant_id).exists():
                self.stderr.write(self.style.ERROR(f"Tenant id={tenant_id} not found."))
                return

        candidates = [
            reservation
            for reservation in qs
            if reservation.adults_count and reservation.guests_count < reservation.adults_count
        ]

        self.stdout.write(
            f"From {from_date}: {len(candidates)} reservation(s) need guest slots."
        )

        total_created = 0
        for reservation in candidates:
            missing = reservation.adults_count - reservation.guests_count
            label = reservation.external_id or reservation.booking_code or reservation.pk
            if options["dry_run"]:
                self.stdout.write(
                    f"  [dry-run] {label} check_in={reservation.check_in} "
                    f"guests={reservation.guests_count}/{reservation.adults_count} "
                    f"(+{missing})"
                )
                continue

            created = ensure_adult_guest_slots(
                tenant=reservation.tenant,
                reservation=reservation,
                adults_count=reservation.adults_count,
            )
            total_created += created
            self.stdout.write(
                f"  {label} check_in={reservation.check_in} +{created} placeholder(s)"
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no changes written."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Done. Created {total_created} placeholder guest(s).")
            )

    @staticmethod
    def _parse_from_date(raw: str) -> date:
        if not raw:
            return timezone.localdate()
        try:
            return date.fromisoformat(raw.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid --from-date {raw!r}; use YYYY-MM-DD.") from exc
