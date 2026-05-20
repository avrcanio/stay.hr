from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.models import MonthlyStatisticsOverride, Reservation
from apps.reservations.sync_versions import (
    build_sync_versions_payload,
    reservations_version,
    statistics_version,
)
from apps.tenants.models import Tenant


class SyncVersionsTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Uzorita", slug="uzorita")
        self.property = Property.objects.create(
            tenant=self.tenant,
            name="Uzorita",
            slug="uzorita",
        )

    def test_empty_tenant_stable_hashes(self):
        payload = build_sync_versions_payload(self.tenant, 2026)
        self.assertIn("reservations", payload)
        self.assertIn("rooms", payload)
        self.assertEqual(len(payload["reservations"]), 16)
        self.assertIn("2026", payload["statistics"])

    def test_reservation_change_bumps_reservations_version(self):
        before = reservations_version(self.tenant)
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 4, 1),
            check_out=date(2026, 4, 5),
            status=Reservation.Status.EXPECTED,
            booker_name="Test",
            amount=Decimal("100.00"),
        )
        after = reservations_version(self.tenant)
        self.assertNotEqual(before, after)

    def test_override_bumps_statistics_version_for_view_year(self):
        before = statistics_version(self.tenant, 2026)
        MonthlyStatisticsOverride.objects.create(
            tenant=self.tenant,
            year=2025,
            month=4,
            revenue=Decimal("5000.00"),
            nights=40,
        )
        after = statistics_version(self.tenant, 2026)
        self.assertNotEqual(before, after)
