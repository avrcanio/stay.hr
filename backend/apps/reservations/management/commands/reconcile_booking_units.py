from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.integrations.channex.booking_room_mismatch import reconcile_reservation_units
from apps.reservations.models import Reservation
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "List reservations where Channex rooms[] or units_count "
        "does not match mapped ReservationUnit rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            type=int,
            default=2,
            help="Tenant primary key (default: 2 = uzorita).",
        )
        parser.add_argument(
            "--booking-code",
            type=str,
            default="",
            help="Filter to a single Booking.com number.",
        )
        parser.add_argument(
            "--only-issues",
            action="store_true",
            help="Print only reservations with detected issues.",
        )

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(pk=options["tenant_id"]).first()
        if tenant is None:
            self.stderr.write(self.style.ERROR(f"Tenant id={options['tenant_id']} not found."))
            return

        booking_code = (options["booking_code"] or "").strip()
        qs = Reservation.objects.filter(tenant=tenant).exclude(
            status=Reservation.Status.CANCELED,
        )
        if booking_code:
            qs = qs.filter(booking_code=booking_code)
        else:
            qs = qs.filter(Q(units_count__gte=2) | Q(import_source="channex"))

        issue_count = 0
        scanned = 0
        for reservation in qs.order_by("check_in", "pk").iterator():
            scanned += 1
            report = reconcile_reservation_units(reservation)
            issues = report.get("issues") or []
            if options["only_issues"] and not issues:
                continue
            if issues:
                issue_count += 1
            self.stdout.write(
                f"#{report['reservation_id']} {report['booking_code']} "
                f"units_count={report['units_count']} mapped={report['mapped_units']} "
                f"channex_rooms={report['channex_rooms']} pdf_locked={report['pdf_locked']}"
            )
            for issue in issues:
                self.stdout.write(self.style.WARNING(f"  ! {issue}"))

        if issue_count:
            self.stdout.write(
                self.style.WARNING(
                    f"Scanned {scanned}, {issue_count} reservation(s) with issues."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Scanned {scanned}, no unit/revision mismatches.")
            )
