from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from apps.properties.models import Property
from apps.reservations.booking_xls_import import BookingXlsRow
from apps.reservations.models import Reservation
from apps.reservations.reports.booking_reconcile_apply import (
    BookingReconcileApplyItem,
    apply_booking_reconcile_fixes,
)
from apps.reservations.reports.booking_reconcile_snapshot import (
    content_sha256_hex,
    load_booking_reconcile_snapshot,
    save_booking_reconcile_snapshot,
    validate_snapshot_scope,
)
from apps.reservations.reports.booking_reconcile_types import (
    BookingFieldKey,
    BookingReconcileParams,
)
from apps.tenants.models import Tenant


def _xls_row(**overrides) -> BookingXlsRow:
    base = dict(
        external_id="5207177825",
        booker_name="Guest, Test",
        guest_names=["Guest, Test"],
        check_in_date=date(2026, 6, 1),
        check_out_date=date(2026, 6, 3),
        booked_at=None,
        booking_status="ok",
        units_count=1,
        persons_count=2,
        adults_count=2,
        children_count=0,
        children_ages="",
        total_amount=Decimal("100.00"),
        currency="EUR",
        commission_percent=Decimal("10.00"),
        commission_amount=Decimal("10.00"),
        payment_status="",
        payment_provider="",
        notes="",
        booker_country="HR",
        travel_purpose="",
        booking_device="",
        room_name="Room A",
        nights_count=2,
        canceled_at=None,
        booker_address="",
        booker_phone="",
    )
    base.update(overrides)
    return BookingXlsRow(**base)


class ApplyBookingReconcileFixesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita-apply")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )
        self.params = BookingReconcileParams(
            tenant=self.tenant,
            property=self.property,
            date_axis="check_out",
            date_from=date(2026, 6, 1),
            date_to_inclusive=date(2026, 6, 30),
            filename="export.xls",
        )
        self.row = _xls_row()
        self.snapshot_id = save_booking_reconcile_snapshot(
            params=self.params,
            xls_rows=[self.row],
            result_rows=(),
            content_sha256="test" * 16,
        )

    def test_fill_empty_commission(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5207177825",
            booking_code="5207177825",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Guest, Test",
            amount=Decimal("100.00"),
            commission_amount=None,
        )

        results = apply_booking_reconcile_fixes(
            tenant=self.tenant,
            property=self.property,
            snapshot_id=self.snapshot_id,
            items=(
                BookingReconcileApplyItem(
                    booking_code="5207177825",
                    fields=(BookingFieldKey.COMMISSION_AMOUNT,),
                ),
            ),
            default_mode="fill_empty",
        )

        self.assertTrue(results[0].applied)
        reservation.refresh_from_db()
        self.assertEqual(reservation.commission_amount, Decimal("10.00"))

    def test_pdf_locked_skipped(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5207177825",
            booking_code="5207177825",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Guest, Test",
            amount=Decimal("100.00"),
            commission_amount=None,
            pdf_imported_at=timezone.now(),
        )

        results = apply_booking_reconcile_fixes(
            tenant=self.tenant,
            property=self.property,
            snapshot_id=self.snapshot_id,
            items=(
                BookingReconcileApplyItem(
                    booking_code="5207177825",
                    fields=(BookingFieldKey.COMMISSION_AMOUNT,),
                ),
            ),
        )

        self.assertFalse(results[0].applied)
        self.assertEqual(results[0].reason, "pdf_locked")
        reservation.refresh_from_db()
        self.assertIsNone(reservation.commission_amount)

    def test_import_missing_in_stay(self):
        results = apply_booking_reconcile_fixes(
            tenant=self.tenant,
            property=self.property,
            snapshot_id=self.snapshot_id,
            items=(BookingReconcileApplyItem(booking_code="5207177825"),),
            default_mode="fill_empty",
        )

        self.assertTrue(results[0].applied)
        reservation = Reservation.objects.get(external_id="5207177825")
        self.assertEqual(reservation.amount, Decimal("100.00"))

    def test_overwrite_requires_confirm(self):
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5207177825",
            booking_code="5207177825",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Guest, Test",
            amount=Decimal("100.00"),
            commission_amount=Decimal("1.00"),
        )

        results = apply_booking_reconcile_fixes(
            tenant=self.tenant,
            property=self.property,
            snapshot_id=self.snapshot_id,
            items=(
                BookingReconcileApplyItem(
                    booking_code="5207177825",
                    fields=(BookingFieldKey.COMMISSION_AMOUNT,),
                    mode="overwrite",
                ),
            ),
            confirm_overwrite=False,
        )

        self.assertEqual(results[0].reason, "overwrite_not_confirmed")

    def test_snapshot_not_found(self):
        results = apply_booking_reconcile_fixes(
            tenant=self.tenant,
            property=self.property,
            snapshot_id="missing",
            items=(BookingReconcileApplyItem(booking_code="5207177825"),),
        )
        self.assertEqual(results[0].reason, "snapshot_not_found")

    def test_snapshot_scope_mismatch(self):
        other = Property.objects.create(
            tenant=self.tenant,
            name="Other",
            slug="other",
        )
        results = apply_booking_reconcile_fixes(
            tenant=self.tenant,
            property=other,
            snapshot_id=self.snapshot_id,
            items=(BookingReconcileApplyItem(booking_code="5207177825"),),
        )
        self.assertEqual(results[0].reason, "snapshot_scope_mismatch")

    def test_snapshot_meta_includes_hash_and_scope(self):
        payload = load_booking_reconcile_snapshot(self.snapshot_id)
        self.assertIsNotNone(payload)
        meta = payload["meta"]
        self.assertEqual(meta["tenant_id"], self.tenant.id)
        self.assertEqual(meta["property_id"], self.property.id)
        self.assertEqual(len(meta["content_sha256"]), 64)
        self.assertIn("created_at", meta)
        self.assertIsNone(
            validate_snapshot_scope(payload, tenant_id=self.tenant.id, property_id=self.property.id)
        )

    @patch("apps.reservations.reports.booking_reconcile_apply._apply_selected_fields")
    def test_unexpected_exception_rolls_back_entire_apply(self, mock_apply_fields):
        reservation_a = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5207177825",
            booking_code="5207177825",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Guest, Test",
            commission_amount=None,
        )
        reservation_b = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="BBB222",
            booking_code="BBB222",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="B",
            commission_amount=None,
        )
        row_b = _xls_row(external_id="BBB222", commission_amount=Decimal("5.00"))
        snapshot_id = save_booking_reconcile_snapshot(
            params=self.params,
            xls_rows=[self.row, row_b],
            result_rows=(),
            content_sha256=content_sha256_hex(b"snapshot"),
        )

        def side_effect(*, reservation, xls_row, fields, mode):
            if reservation.id == reservation_b.id:
                raise RuntimeError("simulated failure")
            reservation.commission_amount = Decimal("10.00")
            reservation.save(update_fields=["commission_amount", "updated_at"])
            return True, "applied"

        mock_apply_fields.side_effect = side_effect

        with self.assertRaises(RuntimeError):
            apply_booking_reconcile_fixes(
                tenant=self.tenant,
                property=self.property,
                snapshot_id=snapshot_id,
                items=(
                    BookingReconcileApplyItem(
                        booking_code="5207177825",
                        fields=(BookingFieldKey.COMMISSION_AMOUNT,),
                    ),
                    BookingReconcileApplyItem(
                        booking_code="BBB222",
                        fields=(BookingFieldKey.COMMISSION_AMOUNT,),
                    ),
                ),
            )

        reservation_a.refresh_from_db()
        reservation_b.refresh_from_db()
        self.assertIsNone(reservation_a.commission_amount)
        self.assertIsNone(reservation_b.commission_amount)

    @patch("apps.reservations.reports.booking_reconcile_apply.logger")
    def test_audit_log_on_apply(self, mock_logger):
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5207177825",
            booking_code="5207177825",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Guest, Test",
            commission_amount=None,
        )
        apply_booking_reconcile_fixes(
            tenant=self.tenant,
            property=self.property,
            snapshot_id=self.snapshot_id,
            items=(
                BookingReconcileApplyItem(
                    booking_code="5207177825",
                    fields=(BookingFieldKey.COMMISSION_AMOUNT,),
                ),
            ),
            applied_by="user:tester",
        )
        self.assertTrue(mock_logger.info.called)
        logged = " ".join(
            str(arg) for call in mock_logger.info.call_args_list for arg in call.args
        )
        self.assertIn("event=booking_reconcile.apply", logged)
        self.assertIn("user:tester", logged)

    def test_reservation_changed_since_compare(self):
        reservation = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5207177825",
            booking_code="5207177825",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Guest, Test",
            commission_amount=None,
        )
        snapshot_id = save_booking_reconcile_snapshot(
            params=self.params,
            xls_rows=[self.row],
            result_rows=(),
            content_sha256=content_sha256_hex(b"snapshot"),
            reservation_fingerprints={"5207177825": "stale-fingerprint"},
        )

        results = apply_booking_reconcile_fixes(
            tenant=self.tenant,
            property=self.property,
            snapshot_id=snapshot_id,
            items=(
                BookingReconcileApplyItem(
                    booking_code="5207177825",
                    fields=(BookingFieldKey.COMMISSION_AMOUNT,),
                ),
            ),
        )

        self.assertEqual(results[0].reason, "reservation_changed_since_compare")
        reservation.refresh_from_db()
        self.assertIsNone(reservation.commission_amount)
