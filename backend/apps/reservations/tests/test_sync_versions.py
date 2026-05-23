from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.properties.models import Property
from apps.reservations.models import Guest, MonthlyStatisticsOverride, Reservation
from apps.reservations.sync_versions import (
    build_sync_versions_payload,
    reservation_detail_version,
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

    def _create_reservation(self, *, booker_name: str = "Test") -> Reservation:
        return Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            check_in=date(2026, 4, 1),
            check_out=date(2026, 4, 5),
            status=Reservation.Status.EXPECTED,
            booker_name=booker_name,
            amount=Decimal("100.00"),
        )

    def test_reservation_detail_version_changes_on_status_update(self):
        reservation = self._create_reservation()
        before = reservation_detail_version(self.tenant, reservation.pk)
        reservation.status = Reservation.Status.CHECKED_IN
        reservation.save(update_fields=["status", "updated_at"])
        after = reservation_detail_version(self.tenant, reservation.pk)
        self.assertNotEqual(before, after)

    def test_reservation_detail_version_unchanged_when_other_reservation_changes(self):
        reservation_a = self._create_reservation(booker_name="A")
        reservation_b = self._create_reservation(booker_name="B")
        before = reservation_detail_version(self.tenant, reservation_a.pk)
        reservation_b.status = Reservation.Status.CHECKED_IN
        reservation_b.save(update_fields=["status", "updated_at"])
        after = reservation_detail_version(self.tenant, reservation_a.pk)
        self.assertEqual(before, after)

    def test_reservation_detail_version_changes_on_guest_update(self):
        reservation = self._create_reservation()
        guest = Guest.objects.create(
            tenant=self.tenant,
            reservation=reservation,
            first_name="Ana",
            last_name="Anić",
            name="Ana Anić",
            is_primary=True,
        )
        before = reservation_detail_version(self.tenant, reservation.pk)
        guest.first_name = "Anamarija"
        guest.save(update_fields=["first_name", "updated_at"])
        after = reservation_detail_version(self.tenant, reservation.pk)
        self.assertNotEqual(before, after)

    def test_build_sync_versions_payload_includes_reservation_detail(self):
        reservation = self._create_reservation()
        payload = build_sync_versions_payload(
            self.tenant,
            2026,
            reservation_id=reservation.pk,
        )
        self.assertIn("reservation_detail", payload)
        self.assertEqual(len(payload["reservation_detail"]), 16)

    def test_build_sync_versions_payload_returns_none_for_missing_reservation(self):
        payload = build_sync_versions_payload(
            self.tenant,
            2026,
            reservation_id=999999,
        )
        self.assertIsNone(payload)
