from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.models import MonthlyStatisticsOverride, Reservation
from apps.reservations.statistics import aggregate_monthly_statistics
from apps.tenants.models import Tenant


class MonthlyStatisticsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita Luxury Rooms",
            slug="uzorita",
        )

    def _create_reservation(self, *, check_in, amount, status, nights=None):
        return Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=check_in,
            check_out=check_in + timedelta(days=nights or 3),
            status=status,
            booker_name="Test Booker",
            amount=amount,
            commission_amount=Decimal("10.00"),
            nights_count=nights or 3,
            currency="EUR",
        )

    def test_aggregate_current_and_previous_year(self):
        self._create_reservation(
            check_in=date(2025, 3, 10),
            amount=Decimal("100.00"),
            status=Reservation.Status.CHECKED_OUT,
        )
        self._create_reservation(
            check_in=date(2026, 3, 15),
            amount=Decimal("200.00"),
            status=Reservation.Status.CHECKED_IN,
        )
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 4, 1),
            check_out=date(2026, 4, 5),
            status=Reservation.Status.EXPECTED,
            booker_name="Expected only",
            amount=Decimal("999.00"),
        )

        payload = aggregate_monthly_statistics(self.tenant, 2026)

        self.assertEqual(payload["property_label"], "Uzorita Luxury Rooms")
        self.assertEqual(payload["year"], 2026)
        self.assertEqual(payload["comparison_year"], 2025)
        self.assertEqual(payload["currency"], "EUR")
        self.assertEqual(len(payload["months"]), 12)

        march = next(m for m in payload["months"] if m["month"] == 3)
        self.assertEqual(march["current"]["revenue"], "200.00")
        self.assertEqual(march["current"]["commission"], "10.00")
        self.assertEqual(march["current"]["nights"], 3)
        self.assertEqual(march["previous"]["revenue"], "100.00")

        april = next(m for m in payload["months"] if m["month"] == 4)
        self.assertEqual(april["current"]["revenue"], "0.00")
        self.assertEqual(april["current"]["nights"], 0)
        self.assertEqual(april["current"]["reserved_revenue"], "999.00")
        self.assertEqual(april["current"]["reserved_nights"], 4)
        self.assertEqual(march["current"]["reserved_revenue"], "200.00")
        self.assertEqual(march["current"]["reserved_nights"], 3)

    def test_expected_increases_reserved_not_realized(self):
        self._create_reservation(
            check_in=date(2026, 6, 1),
            amount=Decimal("500.00"),
            status=Reservation.Status.EXPECTED,
            nights=5,
        )
        payload = aggregate_monthly_statistics(self.tenant, 2026)
        june = next(m for m in payload["months"] if m["month"] == 6)
        self.assertEqual(june["current"]["revenue"], "0.00")
        self.assertEqual(june["current"]["nights"], 0)
        self.assertEqual(june["current"]["reserved_revenue"], "500.00")
        self.assertEqual(june["current"]["reserved_nights"], 5)

    def test_canceled_aggregated_for_current_year_only(self):
        self._create_reservation(
            check_in=date(2026, 5, 12),
            amount=Decimal("400.00"),
            status=Reservation.Status.CANCELED,
            nights=4,
        )
        self._create_reservation(
            check_in=date(2025, 5, 12),
            amount=Decimal("200.00"),
            status=Reservation.Status.CANCELED,
            nights=2,
        )
        payload = aggregate_monthly_statistics(self.tenant, 2026)
        may = next(m for m in payload["months"] if m["month"] == 5)
        self.assertEqual(may["current"]["canceled_revenue"], "400.00")
        self.assertEqual(may["current"]["canceled_nights"], 4)
        self.assertNotIn("canceled_revenue", may["previous"])

    def test_override_does_not_touch_reserved(self):
        self._create_reservation(
            check_in=date(2026, 7, 10),
            amount=Decimal("300.00"),
            status=Reservation.Status.EXPECTED,
            nights=2,
        )
        MonthlyStatisticsOverride.objects.create(
            tenant=self.tenant,
            year=2026,
            month=7,
            revenue=Decimal("9999.00"),
            nights=99,
        )
        payload = aggregate_monthly_statistics(self.tenant, 2026)
        july = next(m for m in payload["months"] if m["month"] == 7)
        self.assertEqual(july["current"]["revenue"], "9999.00")
        self.assertEqual(july["current"]["nights"], 99)
        self.assertEqual(july["current"]["reserved_revenue"], "300.00")
        self.assertEqual(july["current"]["reserved_nights"], 2)

    def test_override_for_comparison_year_without_reservations(self):
        MonthlyStatisticsOverride.objects.create(
            tenant=self.tenant,
            year=2025,
            month=5,
            revenue=Decimal("3580.25"),
            nights=45,
            commission=Decimal("120.00"),
        )
        payload = aggregate_monthly_statistics(self.tenant, 2026)
        may_previous = next(m for m in payload["months"] if m["month"] == 5)["previous"]
        self.assertEqual(may_previous["revenue"], "3580.25")
        self.assertEqual(may_previous["commission"], "120.00")
        self.assertEqual(may_previous["nights"], 45)

    def test_override_replaces_reservation_sum_for_same_month(self):
        self._create_reservation(
            check_in=date(2025, 5, 10),
            amount=Decimal("999.00"),
            status=Reservation.Status.CHECKED_OUT,
            nights=2,
        )
        MonthlyStatisticsOverride.objects.create(
            tenant=self.tenant,
            year=2025,
            month=5,
            revenue=Decimal("3580.25"),
            nights=45,
        )
        payload = aggregate_monthly_statistics(self.tenant, 2026)
        may_previous = next(m for m in payload["months"] if m["month"] == 5)["previous"]
        self.assertEqual(may_previous["revenue"], "3580.25")
        self.assertEqual(may_previous["commission"], "0.00")
        self.assertEqual(may_previous["nights"], 45)

    def test_override_isolated_per_tenant(self):
        other = Tenant.objects.create(name="Demo", slug="demo")
        Property.objects.create(tenant=other, name="Demo", slug="demo")
        MonthlyStatisticsOverride.objects.create(
            tenant=other,
            year=2025,
            month=6,
            revenue=Decimal("5000.00"),
            nights=99,
        )
        payload = aggregate_monthly_statistics(self.tenant, 2026)
        june_previous = next(m for m in payload["months"] if m["month"] == 6)["previous"]
        self.assertEqual(june_previous["revenue"], "0.00")
        self.assertEqual(june_previous["nights"], 0)
