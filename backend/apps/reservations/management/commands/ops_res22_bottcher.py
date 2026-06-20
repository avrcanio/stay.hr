"""Ops flow for reservation #22 (Böttcher / 5281994537) — controlled R1 overbooking 20.6."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError

from apps.core.timezone import property_local_now, tenant_local_now
from apps.integrations.channex.ari_service import (
    apply_availability_updates,
    get_active_channex_integration,
    push_channex_ari,
)
from apps.integrations.channex.exceptions import ChannexBookingIngestError
from apps.integrations.channex.no_show_service import (
    is_channex_no_show_eligible,
    report_no_show_for_reservation,
)
from apps.properties.models import Unit
from apps.reservations.checkout import CheckoutBlockedError, perform_reservation_checkout
from apps.reservations.models import Reservation, ReservationUnit
from apps.reservations.overbooking import find_conflicts
from apps.reservations.reservation_checkin_complete import submit_evisitor_for_reservation
from apps.tenants.models import Tenant

RESERVATION_ID = 22
UNIT_CODE = "R1"
OVERBOOKING_DATE = date(2026, 6, 20)
SUNDAY_ARRIVAL = date(2026, 6, 22)
MONDAY_DECISION = date(2026, 6, 23)
TENANT_ID = 2


class Command(BaseCommand):
    help = (
        "Reservation #22 ops: monitor R1/20.6, Sunday ARI close, conditional check-in, "
        "Monday checkout or no-show."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--step",
            required=True,
            choices=("monitor", "sunday-close-ari", "sunday-arrival", "monday"),
            help="Which phase of the Böttcher flow to run.",
        )
        parser.add_argument(
            "--arrived",
            action="store_true",
            help="For sunday-arrival: guest confirmed they arrived (runs check-in + eVisitor).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip calendar-day guard (ops override only).",
        )

    def handle(self, *args, **options):
        step = options["step"]
        if step == "monitor":
            self._monitor()
        elif step == "sunday-close-ari":
            self._sunday_close_ari(force=options["force"])
        elif step == "sunday-arrival":
            self._sunday_arrival(arrived=options["arrived"], force=options["force"])
        elif step == "monday":
            self._monday(force=options["force"])

    def _reservation(self) -> Reservation:
        try:
            return Reservation.objects.select_related("property", "tenant").get(pk=RESERVATION_ID)
        except Reservation.DoesNotExist as exc:
            raise CommandError(f"Reservation #{RESERVATION_ID} not found.") from exc

    def _local_today(self, reservation: Reservation) -> date:
        return property_local_now(reservation.property).date()

    def _monitor(self) -> None:
        tenant = Tenant.objects.get(pk=TENANT_ID)
        target = OVERBOOKING_DATE
        unit = Unit.objects.get(code=UNIT_CODE, property__slug="uzorita")
        res_ids = ReservationUnit.objects.filter(unit=unit).values_list("reservation_id", flat=True)
        occupants = (
            Reservation.objects.filter(
                pk__in=res_ids,
                check_in__lte=target,
                check_out__gt=target,
            )
            .exclude(status__in=[Reservation.Status.CANCELED, Reservation.Status.NO_SHOW, Reservation.Status.REFUSED])
            .order_by("pk")
        )
        self.stdout.write(f"R1 occupants on {target.isoformat()}:")
        for row in occupants:
            marker = " (Böttcher)" if row.pk == RESERVATION_ID else ""
            self.stdout.write(
                f"  #{row.pk} status={row.status} {row.check_in}-{row.check_out} "
                f"booker={row.booker_name} ext={row.external_id}{marker}"
            )
        new_since_open = occupants.exclude(pk=RESERVATION_ID)
        if new_since_open.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"ALERT: {new_since_open.count()} new R1 booking(s) on {target} — review overbooking."
                )
            )
            for row in new_since_open:
                self.stdout.write(self.style.WARNING(f"  NEW #{row.pk} {row.booker_name} {row.external_id}"))
        else:
            self.stdout.write(self.style.SUCCESS("No new R1 booking on 20.6. besides #22."))

        conflicts = [
            c
            for c in find_conflicts(tenant=tenant, from_date=target)
            if c.unit.code == UNIT_CODE and c.overlap_from <= target < c.overlap_to
        ]
        if conflicts:
            for conflict in conflicts:
                self.stdout.write(
                    self.style.WARNING(
                        f"Overbooking R1 {conflict.overlap_from}..{conflict.overlap_to}: "
                        f"keep #{conflict.incumbent.pk}, action #{conflict.conflicting.pk}"
                    )
                )
        else:
            self.stdout.write(self.style.SUCCESS(f"No R1 overbooking conflict on {target}."))

        from apps.integrations.models import UnitAvailabilityDay

        avail = UnitAvailabilityDay.objects.filter(unit=unit, date=target).values_list("availability", flat=True).first()
        self.stdout.write(f"Local R1 availability {target}: {avail if avail is not None else 'unset'}")

    def _push_r1_availability(self, availability: int) -> None:
        integration = get_active_channex_integration("uzorita")
        updates = [{"unit_code": UNIT_CODE, "date": OVERBOOKING_DATE, "availability": availability}]
        apply_availability_updates(integration, updates, queue_push=True)
        result = push_channex_ari(integration)
        self.stdout.write(f"Channex push availability={availability} for {OVERBOOKING_DATE}: {result}")

    def _sunday_close_ari(self, *, force: bool) -> None:
        reservation = self._reservation()
        today = self._local_today(reservation)
        if today < SUNDAY_ARRIVAL and not force:
            raise CommandError(
                f"sunday-close-ari runs on or after {SUNDAY_ARRIVAL} (today={today}). Use --force to override."
            )
        self.stdout.write(
            f"Closing R1 on {OVERBOOKING_DATE} before Böttcher arrival (res #{RESERVATION_ID})."
        )
        self._push_r1_availability(0)
        self.stdout.write(self.style.SUCCESS("R1 availability=0 pushed for 20.6."))

    def _sunday_arrival(self, *, arrived: bool, force: bool) -> None:
        reservation = self._reservation()
        today = self._local_today(reservation)
        if not arrived:
            self.stdout.write(
                "Guests not confirmed arrived — no check-in, no eVisitor. Waiting until Monday decision."
            )
            self.stdout.write(f"Reservation #{RESERVATION_ID} status remains {reservation.status}.")
            return

        if today < SUNDAY_ARRIVAL and not force:
            raise CommandError(
                f"sunday-arrival --arrived runs on or after {SUNDAY_ARRIVAL} (today={today}). "
                "Use --force to override."
            )
        if reservation.status == Reservation.Status.CHECKED_IN:
            self.stdout.write(self.style.SUCCESS("Already checked in."))
        elif reservation.status != Reservation.Status.EXPECTED:
            raise CommandError(f"Unexpected status {reservation.status}; expected 'expected' or 'checked_in'.")
        else:
            old_status = reservation.status
            reservation.status = Reservation.Status.CHECKED_IN
            reservation.save(update_fields=["status", "updated_at"])
            from apps.core.tasks import notify_reservation_status_changed

            notify_reservation_status_changed.delay(
                reservation.pk,
                old_status,
                reservation.status,
            )
            self.stdout.write(self.style.SUCCESS("Ops check-in complete (bypassed wrong_date guard)."))

        zagreb = ZoneInfo("Europe/Zagreb")
        time_stay_from = datetime(2026, 6, 22, 15, 0, tzinfo=zagreb).strftime("%Y-%m-%dT%H:%M:%S")
        results = submit_evisitor_for_reservation(reservation, time_stay_from=time_stay_from)
        for row in results:
            line = f"  guest #{row.get('guest_id')} {row.get('guest_name')}: {row.get('status')}"
            if row.get("status") in ("validation_failed", "api_error", "config_error"):
                self.stdout.write(self.style.ERROR(line + f" — {row.get('message', '')}"))
            else:
                self.stdout.write(self.style.SUCCESS(line))

        phone = (reservation.booker_phone or "").strip()
        self.stdout.write(
            "WA: confirm arrival and pickup with guest"
            + (f" ({phone})" if phone else "")
            + " — manual Toni message."
        )

    def _monday(self, *, force: bool) -> None:
        reservation = self._reservation()
        today = self._local_today(reservation)
        if today < MONDAY_DECISION and not force:
            raise CommandError(
                f"monday runs on or after {MONDAY_DECISION} (today={today}). Use --force to override."
            )
        reservation.refresh_from_db()
        if reservation.status == Reservation.Status.CHECKED_IN:
            try:
                perform_reservation_checkout(reservation, source="ops_res22_bottcher")
            except CheckoutBlockedError as exc:
                raise CommandError(f"Checkout blocked: {exc.code} — {exc}") from exc
            self.stdout.write(self.style.SUCCESS("Checked out with eVisitor departure."))
            return

        if reservation.status == Reservation.Status.EXPECTED:
            waived_fees = False
            if is_channex_no_show_eligible(reservation):
                integration = get_active_channex_integration(reservation.tenant.slug)
                try:
                    report_no_show_for_reservation(
                        integration,
                        reservation,
                        waived_fees=waived_fees,
                    )
                except ChannexBookingIngestError as exc:
                    raise CommandError(f"Channex no-show failed: {exc}") from exc
            reservation.status = Reservation.Status.NO_SHOW
            reservation.booking_status = "no_show"
            reservation.save(update_fields=["status", "booking_status", "updated_at"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"No-show recorded (waived_fees={waived_fees}) — Booking.com charge per policy."
                )
            )
            return

        raise CommandError(f"Nothing to do for status={reservation.status}.")
