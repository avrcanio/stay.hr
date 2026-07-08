from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.reservations.reports.booking_reconcile_types import (
    BookingDiffSeverity,
    BookingFieldDiff,
    BookingFieldKey,
    BookingReconcileBlockReason,
    BookingReconcileMatchKind,
    BookingReconcileMeta,
    BookingReconcileResult,
    BookingReconcileRow,
    BookingReconcileSummary,
    FIELD_LABELS,
    summarize_booking_reconcile_rows,
)


def _field_diff(**overrides) -> BookingFieldDiff:
    base = dict(
        field_key=BookingFieldKey.COMMISSION_AMOUNT,
        field_label=FIELD_LABELS[BookingFieldKey.COMMISSION_AMOUNT],
        booking_value=Decimal("10.00"),
        stay_value=None,
        booking_display="10,00 €",
        stay_display="—",
        severity=BookingDiffSeverity.WARNING,
        fixable=True,
        block_reasons=(),
    )
    base.update(overrides)
    return BookingFieldDiff(**base)


def _row(**overrides) -> BookingReconcileRow:
    base = dict(
        row_key="1:5207177825",
        booking_code="5207177825",
        booking_external_id="5207177825",
        match_kind=BookingReconcileMatchKind.MATCHED,
        reservation_id=42,
        guest_name="Ana Anić",
        booking_status="ok",
        stay_status="checked_out",
        booking_amount=Decimal("100.00"),
        stay_amount=Decimal("100.00"),
        booking_commission=Decimal("10.00"),
        stay_commission=None,
        check_in=date(2026, 6, 1),
        check_out=date(2026, 6, 3),
        differences=(_field_diff(),),
    )
    base.update(overrides)
    return BookingReconcileRow(**base)


class SummarizeBookingReconcileRowsTests(TestCase):
    def test_counters_and_totals_for_mixed_rows(self):
        rows = (
            _row(
                match_kind=BookingReconcileMatchKind.MATCHED,
                booking_amount=Decimal("100.00"),
                stay_amount=Decimal("100.00"),
                booking_commission=Decimal("10.00"),
                stay_commission=Decimal("9.00"),
            ),
            _row(
                row_key="1:999",
                booking_code="999",
                booking_external_id="999",
                match_kind=BookingReconcileMatchKind.MISSING_IN_STAY,
                reservation_id=None,
                stay_amount=None,
                stay_commission=None,
                booking_amount=Decimal("50.00"),
                booking_commission=Decimal("5.00"),
                differences=(),
            ),
            _row(
                row_key="1:888",
                booking_code="888",
                booking_external_id="888",
                match_kind=BookingReconcileMatchKind.MISSING_IN_BOOKING,
                booking_amount=None,
                booking_commission=None,
                stay_amount=Decimal("75.00"),
                stay_commission=Decimal("7.50"),
                differences=(),
            ),
        )
        summary = summarize_booking_reconcile_rows(rows)
        self.assertEqual(summary.total_rows, 3)
        self.assertEqual(summary.matched, 1)
        self.assertEqual(summary.missing_in_stay, 1)
        self.assertEqual(summary.missing_in_booking, 1)
        self.assertEqual(summary.rows_with_differences, 1)
        self.assertEqual(summary.fixable_rows, 2)
        self.assertEqual(summary.booking_total_amount, Decimal("150.00"))
        self.assertEqual(summary.stay_total_amount, Decimal("175.00"))
        self.assertEqual(summary.booking_total_commission, Decimal("15.00"))
        self.assertEqual(summary.stay_total_commission, Decimal("16.50"))


class BookingReconcileRowHelperTests(TestCase):
    def test_has_differences_and_is_fixable(self):
        row = _row()
        self.assertTrue(row.has_differences)
        self.assertTrue(row.is_fixable)

    def test_missing_in_stay_is_fixable_without_diffs(self):
        row = _row(
            match_kind=BookingReconcileMatchKind.MISSING_IN_STAY,
            reservation_id=None,
            differences=(),
        )
        self.assertFalse(row.has_differences)
        self.assertTrue(row.is_fixable)

    def test_status_diff_is_not_fixable(self):
        row = _row(
            differences=(
                _field_diff(
                    field_key=BookingFieldKey.STATUS,
                    field_label=FIELD_LABELS[BookingFieldKey.STATUS],
                    fixable=False,
                    booking_value="ok",
                    stay_value="expected",
                    booking_display="ok",
                    stay_display="expected",
                ),
            )
        )
        self.assertTrue(row.has_differences)
        self.assertFalse(row.is_fixable)


class BookingReconcileResultHelperTests(TestCase):
    def test_result_helpers_filter_rows(self):
        rows = (
            _row(booking_code="A"),
            _row(
                booking_code="B",
                match_kind=BookingReconcileMatchKind.MISSING_IN_STAY,
                reservation_id=None,
                differences=(),
            ),
            _row(booking_code="C", differences=()),
        )
        summary = BookingReconcileSummary(
            total_rows=3,
            matched=2,
            missing_in_stay=1,
            missing_in_booking=0,
            parse_errors=0,
            rows_with_differences=1,
            fixable_rows=2,
            booking_total_amount=Decimal("0"),
            stay_total_amount=Decimal("0"),
            booking_total_commission=Decimal("0"),
            stay_total_commission=Decimal("0"),
        )
        meta = BookingReconcileMeta(
            tenant_id=1,
            property_id=2,
            property_slug="uzorita",
            filename="export.xls",
            date_axis="check_out",
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
            generated_at=timezone.now(),
            parser_version="booking_xls_import.v1",
        )
        result = BookingReconcileResult(snapshot_id="abc", meta=meta, summary=summary, rows=rows)
        self.assertEqual(len(result.rows_with_differences), 1)
        self.assertEqual(len(result.fixable_rows), 2)


class BookingFieldDiffTests(TestCase):
    def test_block_reasons_tuple(self):
        diff = _field_diff(
            block_reasons=(
                BookingReconcileBlockReason.PDF_LOCKED,
                BookingReconcileBlockReason.STALE_XLS,
            )
        )
        self.assertEqual(len(diff.block_reasons), 2)
        self.assertFalse(diff.fixable is False and diff.block_reasons)


class BookingFieldKeyTests(TestCase):
    def test_field_labels_cover_all_keys(self):
        for key in BookingFieldKey:
            self.assertIn(key, FIELD_LABELS)
            self.assertTrue(FIELD_LABELS[key])


class FrozenContractTests(TestCase):
    def test_enums_serialize_to_string(self):
        self.assertEqual(str(BookingReconcileMatchKind.MATCHED), "matched")
        self.assertEqual(str(BookingDiffSeverity.WARNING), "warning")
        self.assertEqual(str(BookingReconcileBlockReason.PDF_LOCKED), "pdf_locked")
        self.assertEqual(str(BookingFieldKey.AMOUNT), "amount")

    def test_collections_are_immutable_tuples(self):
        row = _row()
        self.assertIsInstance(row.differences, tuple)
        diff = row.differences[0]
        self.assertIsInstance(diff.block_reasons, tuple)
        result = BookingReconcileResult(
            snapshot_id=None,
            meta=BookingReconcileMeta(
                tenant_id=1,
                property_id=1,
                property_slug="x",
                filename="f.xls",
                date_axis=None,
                date_from=None,
                date_to=None,
                generated_at=datetime(2026, 6, 1, tzinfo=dt_timezone.utc),
                parser_version="v1",
            ),
            summary=summarize_booking_reconcile_rows((_row(),)),
            rows=(_row(),),
        )
        self.assertIsInstance(result.rows, tuple)
