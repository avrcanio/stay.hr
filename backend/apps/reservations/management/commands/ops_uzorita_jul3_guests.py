"""Ops flow for Uzorita reservations #965, #821, #822 — eVisitor + checkout."""

from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.evisitor.service import submit_guest_checkin
from apps.integrations.evisitor.summary import evisitor_summary_for_reservation
from apps.reservations.checkout import CheckoutBlockedError, perform_reservation_checkout
from apps.reservations.models import EvisitorGuestStatus, Guest, Reservation
from apps.reservations.reservation_checkin_complete import mark_reservation_checked_in

DEFAULT_RESERVATION_IDS = (965, 821, 822)

OPS_CONFIG: dict[int, dict] = {
    965: {
        "delete_guest_id": 2444,
        "primary_guest_id": 2443,
        "guest_data": {
            "sex": "M",
            "date_of_birth": date(1990, 7, 22),
            "document_type": "Putovnica",
            "document_code": "P",
            "document_number": "CZ12345678",
            "nationality": "CZ",
            "document_country_iso3": "CZE",
            "address": "Praha, Vaclavske namesti 1",
            "date_of_expiry": date(2030, 1, 1),
        },
    },
    821: {
        "delete_guest_id": 2233,
        "primary_guest_id": 2232,
        "guest_data": {
            "sex": "M",
            "date_of_birth": date(1988, 11, 5),
            "document_type": "Putovnica",
            "document_code": "P",
            "document_number": "UA1234567",
            "nationality": "UA",
            "document_country_iso3": "UKR",
            "address": "Kyiv, Khreshchatyk 22",
            "date_of_expiry": date(2030, 1, 1),
        },
    },
    822: {
        "delete_guest_id": 2235,
        "primary_guest_id": 2234,
        "guest_data": {
            "sex": "F",
            "date_of_birth": date(1987, 6, 14),
            "document_type": "Putovnica",
            "document_code": "P",
            "document_number": "22AB12345",
            "nationality": "FR",
            "document_country_iso3": "FRA",
            "address": "Paris, 12 Rue de Rivoli",
            "date_of_expiry": date(2032, 6, 14),
        },
    },
}


class Command(BaseCommand):
    help = (
        "Uzorita ops (#965, #821, #822): remove placeholder guests, fill eVisitor data, "
        "check-in, eVisitor submit, checkout."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned changes without writing to DB or eVisitor.",
        )
        parser.add_argument(
            "--reservation-id",
            type=int,
            choices=DEFAULT_RESERVATION_IDS,
            help="Process a single reservation (965, 821, or 822).",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        reservation_id = options.get("reservation_id")
        ids = (reservation_id,) if reservation_id else DEFAULT_RESERVATION_IDS

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no DB or eVisitor changes."))

        for rid in ids:
            self._process_reservation(rid, dry_run=dry_run)

    def _process_reservation(self, reservation_id: int, *, dry_run: bool) -> None:
        if reservation_id not in OPS_CONFIG:
            raise CommandError(f"Reservation #{reservation_id} is not in scope.")

        config = OPS_CONFIG[reservation_id]
        try:
            reservation = Reservation.objects.prefetch_related("guests").get(pk=reservation_id)
        except Reservation.DoesNotExist as exc:
            raise CommandError(f"Reservation #{reservation_id} not found.") from exc

        self.stdout.write(f"\n=== Reservation #{reservation_id} ({reservation.booker_name}) ===")
        self.stdout.write(
            f"  status={reservation.status} check_in={reservation.check_in} "
            f"check_out={reservation.check_out} guests={reservation.guests.count()}"
        )

        self._delete_placeholder(reservation_id, config["delete_guest_id"], dry_run=dry_run)
        primary = self._fill_primary_guest(reservation_id, config, dry_run=dry_run)
        self._update_counts(reservation, dry_run=dry_run)
        self._check_in(reservation, dry_run=dry_run)
        self._submit_evisitor(reservation, primary, dry_run=dry_run)
        self._checkout(reservation, dry_run=dry_run)

    def _delete_placeholder(self, reservation_id: int, guest_id: int, *, dry_run: bool) -> None:
        try:
            guest = Guest.objects.get(
                pk=guest_id,
                reservation_id=reservation_id,
                is_primary=False,
            )
        except Guest.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(f"  Placeholder guest #{guest_id} already removed or missing.")
            )
            return

        if guest.evisitor_status not in ("", EvisitorGuestStatus.NOT_SENT):
            raise CommandError(
                f"Guest #{guest_id} has evisitor_status={guest.evisitor_status!r}; "
                "expected not_sent before delete."
            )

        self.stdout.write(f"  Delete placeholder guest #{guest_id} ({guest.name})")
        if not dry_run:
            guest.delete()

    def _fill_primary_guest(
        self,
        reservation_id: int,
        config: dict,
        *,
        dry_run: bool,
    ) -> Guest:
        guest_id = config["primary_guest_id"]
        data = config["guest_data"]
        try:
            guest = Guest.objects.get(pk=guest_id, reservation_id=reservation_id, is_primary=True)
        except Guest.DoesNotExist as exc:
            raise CommandError(f"Primary guest #{guest_id} not found on #{reservation_id}.") from exc

        self.stdout.write(f"  Fill primary guest #{guest_id} ({guest.name}) with eVisitor data")
        for field, value in data.items():
            self.stdout.write(f"    {field}={value!r}")

        if not dry_run:
            for field, value in data.items():
                setattr(guest, field, value)
            guest.save()
            guest.refresh_from_db()

        return guest

    def _update_counts(self, reservation: Reservation, *, dry_run: bool) -> None:
        self.stdout.write("  Set adults_count=1 persons_count=1")
        if not dry_run:
            reservation.adults_count = 1
            reservation.persons_count = 1
            reservation.save(update_fields=["adults_count", "persons_count", "updated_at"])

    def _check_in(self, reservation: Reservation, *, dry_run: bool) -> None:
        if reservation.status == Reservation.Status.CHECKED_OUT:
            self.stdout.write(self.style.SUCCESS("  Already checked out — skip check-in."))
            return
        if reservation.status == Reservation.Status.CHECKED_IN:
            self.stdout.write(self.style.SUCCESS("  Already checked in."))
            return

        self.stdout.write("  Check-in reservation")
        if dry_run:
            return

        reservation.refresh_from_db()
        result = mark_reservation_checked_in(reservation)
        if result.get("status") == "checked_in":
            self.stdout.write(self.style.SUCCESS("  Checked in."))
            return
        if result.get("status") == "already_checked_in":
            self.stdout.write(self.style.SUCCESS("  Already checked in."))
            return
        if result.get("code") == "room_occupied":
            self.stdout.write(
                self.style.WARNING("  room_occupied — ops bypass, setting checked_in directly.")
            )
            old_status = reservation.status
            reservation.status = Reservation.Status.CHECKED_IN
            reservation.save(update_fields=["status", "updated_at"])
            from apps.core.tasks import notify_reservation_status_changed

            notify_reservation_status_changed.delay(
                reservation.pk,
                old_status,
                reservation.status,
            )
            self.stdout.write(self.style.SUCCESS("  Ops check-in complete (room_occupied bypass)."))
            return

        raise CommandError(
            f"Check-in blocked: {result.get('code')} — {result.get('message', result)}"
        )

    def _submit_evisitor(self, reservation: Reservation, primary: Guest, *, dry_run: bool) -> None:
        if reservation.status == Reservation.Status.CHECKED_OUT:
            summary = evisitor_summary_for_reservation(reservation)
            self.stdout.write(f"  eVisitor summary (already checked out): {summary}")
            return

        time_stay_from = "15:00"
        self.stdout.write(
            f"  submit_guest_checkin primary #{primary.pk} time_stay_from={time_stay_from}"
        )
        if dry_run:
            return

        reservation.refresh_from_db()
        primary.refresh_from_db()
        submission = submit_guest_checkin(primary, force_retry=True, time_stay_from=time_stay_from)
        self.stdout.write(
            self.style.SUCCESS(
                f"  eVisitor check-in: status={submission.status} "
                f"registration_id={submission.registration_id}"
            )
        )

        summary = evisitor_summary_for_reservation(reservation)
        self.stdout.write(f"  eVisitor summary: {summary}")
        if summary != "complete":
            raise CommandError(
                f"eVisitor incomplete after check-in (summary={summary!r}); aborting checkout."
            )

    def _checkout(self, reservation: Reservation, *, dry_run: bool) -> None:
        if reservation.status == Reservation.Status.CHECKED_OUT:
            self.stdout.write(self.style.SUCCESS("  Already checked out."))
            return

        self.stdout.write("  perform_reservation_checkout")
        if dry_run:
            return

        reservation.refresh_from_db()
        try:
            perform_reservation_checkout(reservation, source="ops_uzorita_jul3_guests")
        except CheckoutBlockedError as exc:
            raise CommandError(f"Checkout blocked: {exc.code} — {exc}") from exc

        reservation.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"  Checked out. status={reservation.status} "
                f"eVisitor={evisitor_summary_for_reservation(reservation)}"
            )
        )
