from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.properties.models import Property
from apps.reservations.booking_xls_import import BookingXlsRow
from apps.reservations.models import Reservation
from apps.reservations.reports.booking_reconcile import compare_booking_export, recompare_from_snapshot
from apps.reservations.reports.booking_reconcile_types import (
    BookingFieldKey,
    BookingReconcileMatchKind,
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


class CompareBookingExportTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita-reconcile")
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

    @patch("apps.reservations.reports.booking_reconcile._parse_rows")
    @patch("apps.reservations.reports.booking_reconcile.save_booking_reconcile_snapshot")
    def test_matched_commission_diff(self, mock_snapshot, mock_parse):
        mock_snapshot.return_value = "snap-1"
        mock_parse.return_value = ([_xls_row()], [])
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
            commission_amount=None,
        )

        result = compare_booking_export(params=self.params, content=b"xls", store_snapshot=True)

        self.assertEqual(result.snapshot_id, "snap-1")
        self.assertEqual(result.summary.matched, 1)
        self.assertEqual(result.summary.rows_with_differences, 1)
        row = result.rows[0]
        self.assertEqual(row.match_kind, BookingReconcileMatchKind.MATCHED)
        keys = {diff.field_key for diff in row.differences}
        self.assertIn(BookingFieldKey.COMMISSION_AMOUNT, keys)

    @patch("apps.reservations.reports.booking_reconcile._parse_rows")
    @patch("apps.reservations.reports.booking_reconcile.save_booking_reconcile_snapshot")
    def test_missing_in_stay(self, mock_snapshot, mock_parse):
        mock_snapshot.return_value = "snap-2"
        mock_parse.return_value = ([_xls_row(external_id="7770001")], [])

        result = compare_booking_export(params=self.params, content=b"xls", store_snapshot=True)

        self.assertEqual(result.summary.missing_in_stay, 1)
        self.assertTrue(result.rows[0].is_fixable)

    @patch("apps.reservations.reports.booking_reconcile._parse_rows")
    @patch("apps.reservations.reports.booking_reconcile.save_booking_reconcile_snapshot")
    def test_stay_only_in_period(self, mock_snapshot, mock_parse):
        mock_snapshot.return_value = "snap-3"
        mock_parse.return_value = ([], [])
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="8120000",
            booking_code="8120000",
            check_in=date(2026, 6, 10),
            check_out=date(2026, 6, 12),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Stay Only",
            amount=Decimal("80.00"),
        )

        result = compare_booking_export(params=self.params, content=b"xls", store_snapshot=True)

        self.assertEqual(result.summary.missing_in_booking, 1)
        self.assertEqual(result.rows[0].booking_code, "8120000")

    @patch("apps.reservations.reports.booking_reconcile._parse_rows")
    @patch("apps.reservations.reports.booking_reconcile.save_booking_reconcile_snapshot")
    def test_pdf_locked_blocks_commission_fix(self, mock_snapshot, mock_parse):
        mock_snapshot.return_value = "snap-4"
        mock_parse.return_value = ([_xls_row()], [])
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
            commission_amount=None,
            pdf_imported_at=timezone.now(),
        )

        result = compare_booking_export(params=self.params, content=b"xls", store_snapshot=True)
        commission_diff = next(
            d for d in result.rows[0].differences if d.field_key is BookingFieldKey.COMMISSION_AMOUNT
        )
        self.assertIn("pdf_locked", [str(r) for r in commission_diff.block_reasons])

    @patch("apps.reservations.reports.booking_reconcile._parse_rows")
    @patch("apps.reservations.reports.booking_reconcile.save_booking_reconcile_snapshot")
    def test_decimal_scale_not_reported_as_diff(self, mock_snapshot, mock_parse):
        mock_snapshot.return_value = "snap-decimal"
        mock_parse.return_value = ([_xls_row(total_amount=Decimal("100.00"))], [])
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            external_id="5207177825",
            booking_code="5207177825",
            check_in=date(2026, 6, 1),
            check_out=date(2026, 6, 3),
            status=Reservation.Status.CHECKED_OUT,
            booker_name="Guest, Test",
            amount=Decimal("100"),
            commission_amount=Decimal("10.00"),
        )

        result = compare_booking_export(params=self.params, content=b"xls", store_snapshot=True)

        row = result.rows[0]
        amount_diffs = [d for d in row.differences if d.field_key is BookingFieldKey.AMOUNT]
        commission_diffs = [
            d for d in row.differences if d.field_key is BookingFieldKey.COMMISSION_AMOUNT
        ]
        self.assertEqual(amount_diffs, [])
        self.assertEqual(commission_diffs, [])

    @patch("apps.reservations.reports.booking_reconcile._parse_rows")
    @patch("apps.reservations.reports.booking_reconcile.save_booking_reconcile_snapshot")
    def test_period_filter_excludes_out_of_range_xls(self, mock_snapshot, mock_parse):
        mock_snapshot.return_value = "snap-5"
        mock_parse.return_value = (
            [
                _xls_row(
                    external_id="out-of-range",
                    check_in_date=date(2026, 7, 1),
                    check_out_date=date(2026, 7, 3),
                )
            ],
            [],
        )

        result = compare_booking_export(params=self.params, content=b"xls", store_snapshot=True)

        self.assertEqual(result.summary.total_rows, 0)

    @patch("apps.reservations.reports.booking_reconcile._parse_rows")
    def test_recompare_from_snapshot(self, mock_parse):
        mock_parse.return_value = ([_xls_row()], [])
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
            commission_amount=None,
        )
        first = compare_booking_export(params=self.params, content=b"xls", store_snapshot=True)
        self.assertIsNotNone(first.snapshot_id)

        second = recompare_from_snapshot(snapshot_id=first.snapshot_id, store_snapshot=True)

        self.assertNotEqual(second.snapshot_id, first.snapshot_id)
        self.assertEqual(second.summary.matched, 1)
        self.assertEqual(second.summary.rows_with_differences, 1)
