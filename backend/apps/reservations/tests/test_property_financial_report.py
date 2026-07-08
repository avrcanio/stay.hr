from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.properties.models import Property, Unit
from apps.reservations.models import Guest, Reservation, ReservationUnit
from apps.reservations.reports.property_financial_report import build_property_financial_report
from apps.reservations.reports.types import (
    PayoutStatus,
    PropertyFinancialReportParams,
    PropertyFinancialReportParamsError,
)
from apps.tenants.models import Tenant


class PropertyFinancialReportServiceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita Luxury Rooms",
            slug="uzorita",
        )
        self.other_property = Property.objects.create(
            tenant=self.tenant,
            name="Other Property",
            slug="other",
        )

    def _params(self, *, check_out_from, check_out_to):
        return PropertyFinancialReportParams(
            tenant=self.tenant,
            property=self.property,
            check_out_from=check_out_from,
            check_out_to_exclusive=check_out_to + timedelta(days=1),
        )

    def _create_reservation(
        self,
        *,
        check_in,
        check_out,
        status=Reservation.Status.CHECKED_OUT,
        amount=Decimal("100.00"),
        commission_amount=Decimal("10.00"),
        nights=None,
        property_obj=None,
        booking_code="BK-1",
    ):
        return Reservation.objects.create(
            tenant=self.tenant,
            property=property_obj or self.property,
            booking_code=booking_code,
            external_id=f"ext-{booking_code}",
            check_in=check_in,
            check_out=check_out,
            status=status,
            booker_name="Test Booker",
            amount=amount,
            commission_amount=commission_amount,
            nights_count=nights or (check_out - check_in).days,
            currency="EUR",
        )

    def _create_unit(self, code: str) -> Unit:
        return Unit.objects.create(
            tenant=self.tenant,
            property=self.property,
            code=code,
            name=f"Room {code}",
            is_active=True,
        )

    def test_includes_checked_out_in_range(self):
        reservation = self._create_reservation(
            check_in=date(2026, 3, 10),
            check_out=date(2026, 3, 13),
            amount=Decimal("200.00"),
            commission_amount=Decimal("20.00"),
            nights=3,
            booking_code="IN-RANGE",
        )
        unit = self._create_unit("101")
        ReservationUnit.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            unit=unit,
            sort_order=0,
            room_name="Soba 101",
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Ana",
            last_name="Anić",
            nationality="HR",
            is_primary=True,
        )
        Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Marko",
            last_name="Marković",
            nationality="DE",
            is_primary=False,
        )

        result = build_property_financial_report(
            self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        )

        self.assertEqual(result.totals.reservation_count, 1)
        self.assertEqual(result.totals.nights, 3)
        self.assertEqual(result.totals.gross, Decimal("200.00"))
        self.assertEqual(result.totals.commission, Decimal("20.00"))
        self.assertEqual(result.totals.net, Decimal("180.00"))
        self.assertEqual(result.meta.rows_with_missing_commission, 0)
        self.assertEqual(result.meta.rows_without_confirmed_payout, 0)

        row = result.rows[0]
        self.assertEqual(row.reservation_id, reservation.id)
        self.assertEqual(row.booking_code, "IN-RANGE")
        self.assertEqual(row.room_labels, ("Soba 101",))
        self.assertEqual(len(row.guests), 2)
        self.assertTrue(row.guests[0].is_primary)
        self.assertEqual(row.guests[0].nationality_iso2, "HR")

    def test_excludes_non_checked_out_statuses(self):
        self._create_reservation(
            check_in=date(2026, 3, 5),
            check_out=date(2026, 3, 8),
            status=Reservation.Status.CHECKED_IN,
            booking_code="CHECKED-IN",
        )
        self._create_reservation(
            check_in=date(2026, 3, 5),
            check_out=date(2026, 3, 8),
            status=Reservation.Status.EXPECTED,
            booking_code="EXPECTED",
        )
        self._create_reservation(
            check_in=date(2026, 3, 5),
            check_out=date(2026, 3, 8),
            status=Reservation.Status.NO_SHOW,
            booking_code="NO-SHOW",
        )
        self._create_reservation(
            check_in=date(2026, 3, 5),
            check_out=date(2026, 3, 8),
            status=Reservation.Status.CANCELED,
            booking_code="CANCELED",
        )

        result = build_property_financial_report(
            self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        )
        self.assertEqual(result.totals.reservation_count, 0)

    def test_check_in_in_range_but_check_out_outside_excluded(self):
        self._create_reservation(
            check_in=date(2026, 3, 25),
            check_out=date(2026, 4, 2),
            booking_code="APRIL-CO",
        )

        result = build_property_financial_report(
            self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        )
        self.assertEqual(result.totals.reservation_count, 0)

    def test_half_open_boundary_on_last_day_of_month(self):
        on_boundary = self._create_reservation(
            check_in=date(2026, 3, 28),
            check_out=date(2026, 3, 31),
            booking_code="MAR-31",
        )
        after_boundary = self._create_reservation(
            check_in=date(2026, 3, 29),
            check_out=date(2026, 4, 1),
            booking_code="APR-1",
        )

        result = build_property_financial_report(
            self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        )

        ids = {row.reservation_id for row in result.rows}
        self.assertIn(on_boundary.id, ids)
        self.assertNotIn(after_boundary.id, ids)

    def test_missing_commission_yields_null_net_and_meta_count(self):
        self._create_reservation(
            check_in=date(2026, 3, 1),
            check_out=date(2026, 3, 4),
            commission_amount=None,
            booking_code="NO-COMM",
        )

        result = build_property_financial_report(
            self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        )

        self.assertEqual(result.rows[0].net, None)
        self.assertEqual(result.meta.rows_with_missing_commission, 1)
        self.assertEqual(result.totals.net, Decimal("0"))

    def test_booking_without_payout_is_not_paid_and_increments_meta(self):
        self._create_reservation(
            check_in=date(2026, 3, 1),
            check_out=date(2026, 3, 4),
            booking_code="BK-UNPAID",
            amount=Decimal("120.00"),
            commission_amount=Decimal("12.00"),
        )
        Reservation.objects.filter(booking_code="BK-UNPAID").update(source="booking.com")

        result = build_property_financial_report(
            self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        )

        row = result.rows[0]
        self.assertEqual(row.payout_status, PayoutStatus.NOT_PAID)
        self.assertIsNone(row.payout_received_at)
        self.assertIsNone(row.paid_amount)
        self.assertEqual(result.meta.rows_without_confirmed_payout, 1)

    def test_booking_with_payout_is_paid(self):
        reservation = self._create_reservation(
            check_in=date(2026, 3, 1),
            check_out=date(2026, 3, 4),
            booking_code="BK-PAID",
            amount=Decimal("120.00"),
            commission_amount=Decimal("12.00"),
        )
        Reservation.objects.filter(pk=reservation.pk).update(
            source="booking.com",
            booking_payout_received_at=date(2026, 4, 5),
            booking_payout_net=Decimal("105.50"),
        )

        result = build_property_financial_report(
            self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        )

        row = result.rows[0]
        self.assertEqual(row.payout_status, PayoutStatus.PAID)
        self.assertEqual(row.payout_received_at, date(2026, 4, 5))
        self.assertEqual(row.paid_amount, Decimal("105.50"))
        self.assertEqual(result.meta.rows_without_confirmed_payout, 0)

    def test_direct_reservation_payout_not_applicable(self):
        self._create_reservation(
            check_in=date(2026, 3, 1),
            check_out=date(2026, 3, 4),
            booking_code="DIRECT-1",
            amount=Decimal("90.00"),
            commission_amount=Decimal("0.00"),
        )
        Reservation.objects.filter(booking_code="DIRECT-1").update(source="direct")

        result = build_property_financial_report(
            self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        )

        row = result.rows[0]
        self.assertEqual(row.payout_status, PayoutStatus.NOT_APPLICABLE)
        self.assertIsNone(row.payout_received_at)
        self.assertIsNone(row.paid_amount)
        self.assertEqual(result.meta.rows_without_confirmed_payout, 0)

    def test_filters_by_property(self):
        self._create_reservation(
            check_in=date(2026, 3, 1),
            check_out=date(2026, 3, 4),
            property_obj=self.property,
            booking_code="MAIN",
        )
        self._create_reservation(
            check_in=date(2026, 3, 1),
            check_out=date(2026, 3, 4),
            property_obj=self.other_property,
            booking_code="OTHER",
        )

        result = build_property_financial_report(
            self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        )
        self.assertEqual(result.totals.reservation_count, 1)
        self.assertEqual(result.rows[0].booking_code, "MAIN")

    @override_settings(PROPERTY_FINANCIAL_REPORT_MAX_DAYS=90)
    def test_period_too_long(self):
        params = PropertyFinancialReportParams(
            tenant=self.tenant,
            property=self.property,
            check_out_from=date(2026, 1, 1),
            check_out_to_exclusive=date(2026, 7, 1),
        )
        with self.assertRaises(PropertyFinancialReportParamsError) as ctx:
            params.validate()
        self.assertEqual(ctx.exception.code, "period_too_long")
        self.assertEqual(ctx.exception.max_days, 90)

    def test_period_invalid_when_to_before_from(self):
        params = PropertyFinancialReportParams(
            tenant=self.tenant,
            property=self.property,
            check_out_from=date(2026, 3, 31),
            check_out_to_exclusive=date(2026, 3, 1),
        )
        with self.assertRaises(PropertyFinancialReportParamsError) as ctx:
            params.validate()
        self.assertEqual(ctx.exception.code, "period_invalid")

    def test_multi_property_tenant_without_slug_raises(self):
        with self.assertRaises(PropertyFinancialReportParamsError) as ctx:
            PropertyFinancialReportParams.from_query(
                self.tenant,
                property_slug=None,
                check_out_from="2026-03-01",
                check_out_to="2026-03-31",
            )
        self.assertEqual(ctx.exception.code, "property_required")

    def test_from_query_normalizes_inclusive_to(self):
        params = PropertyFinancialReportParams.from_query(
            self.tenant,
            property_slug="uzorita",
            check_out_from="2026-03-01",
            check_out_to="2026-03-31",
        )
        self.assertEqual(params.check_out_from, date(2026, 3, 1))
        self.assertEqual(params.check_out_to_exclusive, date(2026, 4, 1))
        self.assertEqual(params.check_out_to_inclusive, date(2026, 3, 31))

    def test_rows_ordered_by_check_out_check_in_id(self):
        later_check_in = self._create_reservation(
            check_in=date(2026, 3, 5),
            check_out=date(2026, 3, 15),
            booking_code="LATER-CI",
        )
        earlier_check_in = self._create_reservation(
            check_in=date(2026, 3, 1),
            check_out=date(2026, 3, 15),
            booking_code="EARLIER-CI",
        )
        earlier_check_out = self._create_reservation(
            check_in=date(2026, 3, 1),
            check_out=date(2026, 3, 10),
            booking_code="EARLIER-CO",
        )

        result = build_property_financial_report(
            self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        )

        self.assertEqual(
            [row.reservation_id for row in result.rows],
            [
                earlier_check_out.id,
                earlier_check_in.id,
                later_check_in.id,
            ],
        )

    def test_query_count_does_not_scale_with_row_count(self):
        for index in range(5):
            self._create_reservation(
                check_in=date(2026, 3, 1),
                check_out=date(2026, 3, 3 + index),
                booking_code=f"Q-{index}",
            )

        params = self._params(check_out_from=date(2026, 3, 1), check_out_to=date(2026, 3, 31))
        with self.assertNumQueries(3):
            build_property_financial_report(params)
