from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.models import Reservation
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
